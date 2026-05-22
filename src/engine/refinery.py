"""LLM payload refinery - compact, structured context bundles for agents.

Independent pipeline:
  - normalize the current task
  - inspect the workspace and detect the tech stack
  - retrieve the highest-signal memory evidence from L1/L2
  - distill rules and skills into compact summaries
  - enforce a fixed context budget before the next LLM call
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path

from src.config import CHROMA_OP_TIMEOUT, TECH_STACKS_DIR
from src.db.chroma_manager import ChromaManager, get_manager
from src.engine.stack_detector import detect_stack_enhanced, read_knowledge

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = "llm-payload/v1"
_DEFAULT_CONTEXT_TOKENS = 3500
_MIN_CONTEXT_TOKENS = 512
_MAX_CONTEXT_TOKENS = 12000
_MAX_MEMORY_ITEMS = 6
_MAX_SUMMARY_LINES = 8
_SUMMARY_CHAR_LIMIT = 1000
_ASYNC_TIMEOUT = CHROMA_OP_TIMEOUT + 5
_NEAR_TIE_DISTANCE = 0.08
_TIER_NEAR_TIE_BONUS: dict[str, float] = {
    "SESSION_LOCAL": 0.045,
    "L1_LOCAL": 0.02,
    "L2_GLOBAL": 0.0,
}
_TIER_RANK: dict[str, int] = {
    "SESSION_LOCAL": 0,
    "L1_LOCAL": 1,
    "L2_GLOBAL": 2,
}

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "before",
        "by",
        "cho",
        "context",
        "cua",
        "de",
        "du",
        "for",
        "from",
        "gateway",
        "hay",
        "is",
        "it",
        "khi",
        "khong",
        "la",
        "llm",
        "mcp",
        "nay",
        "neu",
        "nhat",
        "nhieu",
        "nhung",
        "nhu",
        "payload",
        "the",
        "this",
        "to",
        "tool",
        "va",
        "voi",
    }
)

_mgr: ChromaManager | None = None


def _get_mgr() -> ChromaManager:
    """Return the singleton Chroma manager."""
    global _mgr  # noqa: PLW0603
    if _mgr is None:
        _mgr = get_manager()
    return _mgr


def _estimate_tokens(text: str) -> int:
    """Estimate tokens with a cheap 4 chars/token heuristic."""
    if not text.strip():
        return 0
    return max(1, (len(text) + 3) // 4)


def _clip_text(text: str, max_chars: int) -> str:
    """Trim text to a character budget while keeping words intact."""
    cleaned = text.strip()
    if not cleaned or max_chars <= 0:
        return ""
    if len(cleaned) <= max_chars:
        return cleaned
    clipped = cleaned[: max_chars - 4].rsplit(" ", 1)[0].strip()
    if not clipped:
        clipped = cleaned[: max_chars - 4].strip()
    return f"{clipped} ..."


def _normalize_whitespace(text: str) -> str:
    """Collapse empty-space noise without flattening all newlines."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _normalize_intent(user_input: str) -> str:
    """Map the current task to a coarse intent label."""
    lowered = user_input.lower()
    patterns = [
        ("architecture_upgrade", ("architecture", "gateway", "nang cap", "upgrade", "token", "payload")),
        ("bug_fix", ("bug", "error", "fix", "crash", "failing", "regression")),
        ("code_review", ("review", "audit")),
        ("explanation", ("explain", "tai sao", "what is", "how does")),
        ("refactor", ("refactor", "clean up", "restructure")),
        ("implementation", ("implement", "add", "tao", "them", "xay dung", "build")),
    ]
    for label, keywords in patterns:
        if any(keyword in lowered for keyword in keywords):
            return label
    return "general_request"


def _extract_signal_terms(user_input: str, max_terms: int = 8) -> list[str]:
    """Extract a few high-signal terms from the current request."""
    counts: dict[str, int] = {}
    for token in re.findall(r"[a-zA-Z0-9_./-]+", user_input.lower()):
        if len(token) < 3 or token in _STOP_WORDS:
            continue
        counts[token] = counts.get(token, 0) + 1

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [term for term, _ in ranked[:max_terms]]


def _summarize_markdown(
    content: str,
    max_lines: int = _MAX_SUMMARY_LINES,
    max_chars: int = _SUMMARY_CHAR_LIMIT,
) -> str:
    """Extract high-signal headings and bullet points from markdown."""
    collected: list[str] = []
    seen: set[str] = set()

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("```"):
            continue

        candidate = ""
        if line.startswith(("# ", "## ", "### ")):
            candidate = f"Section: {line.lstrip('#').strip()}"
        elif line.startswith(("- ", "* ")):
            candidate = line[2:].strip()
        elif re.match(r"^\d+\.\s+", line):
            candidate = line
        elif len(collected) < 2:
            candidate = line

        candidate = re.sub(r"\s+", " ", candidate).strip()
        if not candidate:
            continue
        if len(candidate) > 160:
            candidate = _clip_text(candidate, 160)
        if candidate in seen:
            continue

        rendered = "\n".join(collected + [f"- {candidate}"])
        if len(rendered) > max_chars:
            break

        collected.append(f"- {candidate}")
        seen.add(candidate)
        if len(collected) >= max_lines:
            break

    return "\n".join(collected)


def _build_block(
    kind: str,
    title: str,
    content: str,
    source: str,
    priority: float,
    trust: str,
    truncatable: bool = True,
) -> dict:
    """Create a normalized payload block."""
    return {
        "kind": kind,
        "title": title,
        "content": _normalize_whitespace(content),
        "source": source,
        "priority": round(priority, 2),
        "trust": trust,
        "truncatable": truncatable,
    }


def _render_block(block: dict) -> str:
    """Render a block into a compact text segment for the next LLM call."""
    return (
        f"[{block['kind']}] {block['title']}\n"
        f"source={block['source']} trust={block['trust']} priority={block['priority']}\n"
        f"{block['content']}"
    ).strip()


def _score_from_distance(distance: float) -> float:
    """Translate semantic-search distance to a coarse priority score."""
    bounded = max(0.0, min(distance, 1.5))
    return max(0.45, round(0.92 - (bounded * 0.25), 2))


def _query_memory_tier(
    tier_label: str,
    collection_getter,
    query: str,
    n_results: int,
    where_filter: dict | None,
) -> list[dict]:
    """Query a single memory tier and return structured hits."""
    results: list[dict] = []
    mgr = _get_mgr()
    try:
        collection = collection_getter()
        count = collection.count()
        if count <= 0:
            return results

        raw = collection.query(
            query_texts=[query],
            n_results=min(n_results, count),
            where=where_filter,
        )
        docs = raw["documents"][0] if raw.get("documents") else []
        metas = raw["metadatas"][0] if raw.get("metadatas") else []
        dists = raw["distances"][0] if raw.get("distances") else []

        for index, doc in enumerate(docs):
            results.append(
                {
                    "tier": tier_label,
                    "document": doc,
                    "metadata": metas[index] if index < len(metas) else {},
                    "distance": dists[index] if index < len(dists) else 999.0,
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("prepare_llm_payload %s query failed: %s", tier_label, exc)
        mgr.reset()
    return results


def _query_specs_for_scope(
    mgr: ChromaManager,
    workspace_id: str,
    memory_scope: str,
    session_namespace: str | None,
) -> list[tuple[str, object, dict | None]]:
    """Build local-scope query specs for refinery retrieval."""
    if memory_scope == "session":
        if not session_namespace:
            return []
        return [
            ("SESSION_LOCAL", lambda: mgr.get_session_direct(session_namespace), None),
            ("L1_LOCAL", lambda: mgr.get_l1_direct(workspace_id), None),
        ]
    if memory_scope == "workspace":
        return [("L1_LOCAL", lambda: mgr.get_l1_direct(workspace_id), None)]
    return []


def _run_query_specs(
    query: str,
    max_items: int,
    query_specs: list[tuple[str, object, dict | None]],
) -> list[dict]:
    """Run a list of tier queries in parallel and merge all hits."""
    mgr = _get_mgr()
    futures = [
        (
            tier_label,
            mgr._query_executor.submit(
                _query_memory_tier,
                tier_label,
                getter,
                query,
                max_items,
                where_filter,
            ),
        )
        for tier_label, getter, where_filter in query_specs
    ]

    combined: list[dict] = []
    for _tier_label, future in futures:
        try:
            combined.extend(future.result(timeout=CHROMA_OP_TIMEOUT))
        except Exception:  # noqa: BLE001
            continue
    return combined


def _adjusted_distance_for_tier(
    distance: float,
    tier: str,
    best_distance: float,
) -> float:
    """Apply a small near-tie bonus for local tiers without masking large gaps."""
    bonus = _TIER_NEAR_TIE_BONUS.get(tier, 0.0)
    if bonus <= 0.0:
        return distance
    if (distance - best_distance) > _NEAR_TIE_DISTANCE:
        return distance
    return max(0.0, distance - bonus)


def _rank_memory_hits(hits: list[dict], max_items: int) -> list[dict]:
    """Rank hits by semantic distance with scope-aware near-tie preference."""
    if not hits:
        return []
    best_distance = min(item["distance"] for item in hits)

    def _sort_key(item: dict) -> tuple[float, float, int]:
        adjusted = _adjusted_distance_for_tier(
            item["distance"],
            item["tier"],
            best_distance,
        )
        return (adjusted, item["distance"], _TIER_RANK.get(item["tier"], 99))

    ranked = sorted(hits, key=_sort_key)
    return ranked[:max_items]


def _collect_memory_hits(
    query: str,
    workspace_id: str,
    tech_stack: str | None,
    max_items: int,
    memory_scope: str = "workspace",
    session_namespace: str | None = None,
) -> list[dict]:
    """Collect local+global evidence with tier-aware filtering and ranking."""
    mgr = _get_mgr()
    if memory_scope == "session" and not session_namespace:
        return []
    local_query_specs = _query_specs_for_scope(
        mgr,
        workspace_id,
        memory_scope,
        session_namespace,
    )

    local_hits = _run_query_specs(query, max_items, local_query_specs)

    global_filter = {"tech_stack": tech_stack} if tech_stack else None
    global_hits = _run_query_specs(
        query,
        max_items,
        [("L2_GLOBAL", mgr.get_l2_direct, global_filter)],
    )
    if tech_stack and not global_hits:
        global_hits = _run_query_specs(
            query,
            max_items,
            [("L2_GLOBAL", mgr.get_l2_direct, None)],
        )

    return _rank_memory_hits(local_hits + global_hits, max_items)


def _fetch_memory_blocks(
    query: str,
    workspace_id: str,
    tech_stack: str | None,
    max_items: int = _MAX_MEMORY_ITEMS,
    memory_scope: str = "workspace",
    session_namespace: str | None = None,
) -> tuple[list[dict], str]:
    """Return the best memory blocks for the current task."""
    mgr = _get_mgr()
    try:
        mgr.connect()
    except (ConnectionError, TimeoutError) as exc:
        logger.info("prepare_llm_payload memory unavailable: %s", exc)
        return [], "unavailable"

    hits = _collect_memory_hits(
        query,
        workspace_id,
        tech_stack,
        max_items,
        memory_scope=memory_scope,
        session_namespace=session_namespace,
    )
    if not hits:
        return [], "empty"

    blocks: list[dict] = []
    for hit in hits:
        meta = hit["metadata"]
        source = meta.get("source", "unknown")
        title = f"{hit['tier']} memory from {source}"
        content = _clip_text(hit["document"], 900)
        blocks.append(
            _build_block(
                kind="memory",
                title=title,
                content=content,
                source=hit["tier"],
                priority=_score_from_distance(hit["distance"]),
                trust="medium" if hit["tier"] == "L2_GLOBAL" else "high",
            )
        )
    return blocks, "ready"


def _build_workspace_blocks(
    workspace_path: Path,
    requested_stack: str | None,
) -> tuple[dict, list[dict]]:
    """Collect workspace facts plus compact tech-stack knowledge blocks."""
    detection = detect_stack_enhanced(workspace_path, TECH_STACKS_DIR)
    detected_stack = detection["stack"]
    effective_stack = requested_stack or detected_stack

    if requested_stack:
        detection_method = (
            "explicit"
            if requested_stack != detected_stack
            else f"explicit + {detection['method']}"
        )
    else:
        detection_method = detection["method"]

    blocks: list[dict] = []
    available_references: list[str] = []
    workspace_summary = (
        f"Project name: {workspace_path.name}\n"
        f"Detected stack: {effective_stack or 'unknown'}\n"
        f"Detection method: {detection_method}\n"
        f"Confidence: {detection['confidence']}"
    )
    blocks.append(
        _build_block(
            kind="workspace_fact",
            title="Workspace snapshot",
            content=workspace_summary,
            source="workspace_scan",
            priority=0.96,
            trust="high",
            truncatable=False,
        )
    )

    stack_dir = TECH_STACKS_DIR / effective_stack if effective_stack else None
    if effective_stack and stack_dir and stack_dir.is_dir():
        knowledge = read_knowledge(effective_stack, TECH_STACKS_DIR)
        rules_summary = _summarize_markdown(str(knowledge.get("rules.md", "")))
        skills_summary = _summarize_markdown(str(knowledge.get("skills.md", "")))
        available_references = list(knowledge.get("available_references", []))

        if rules_summary:
            blocks.append(
                _build_block(
                    kind="knowledge_rules",
                    title=f"{effective_stack} rules summary",
                    content=rules_summary,
                    source=f"tech_stacks/{effective_stack}/rules.md",
                    priority=0.88,
                    trust="high",
                )
            )
        if skills_summary:
            blocks.append(
                _build_block(
                    kind="knowledge_skills",
                    title=f"{effective_stack} skills summary",
                    content=skills_summary,
                    source=f"tech_stacks/{effective_stack}/skills.md",
                    priority=0.82,
                    trust="high",
                )
            )
        if available_references:
            reference_text = ", ".join(available_references[:8])
            if len(available_references) > 8:
                reference_text += ", ..."
            blocks.append(
                _build_block(
                    kind="references",
                    title="Available deep-dive references",
                    content=reference_text,
                    source=f"tech_stacks/{effective_stack}/references",
                    priority=0.6,
                    trust="high",
                )
            )

    workspace_meta = {
        "path": str(workspace_path),
        "tech_stack": effective_stack or "unknown",
        "detected_stack": detected_stack or "unknown",
        "detection_method": detection_method,
        "confidence": detection["confidence"],
        "available_references": available_references,
    }
    return workspace_meta, blocks


def _fit_blocks_to_budget(
    blocks: list[dict],
    max_context_tokens: int,
) -> tuple[list[dict], list[dict], int]:
    """Select the highest-signal blocks while respecting the token budget."""
    selected: list[dict] = []
    dropped: list[dict] = []
    used_tokens = 0

    for raw_block in sorted(blocks, key=lambda block: (-block["priority"], block["title"])):
        block = dict(raw_block)
        rendered = _render_block(block)
        token_estimate = _estimate_tokens(rendered)

        if used_tokens + token_estimate <= max_context_tokens:
            block["id"] = f"ctx_{len(selected) + 1:02d}"
            block["token_estimate"] = token_estimate
            block.pop("truncatable", None)
            selected.append(block)
            used_tokens += token_estimate
            continue

        remaining_tokens = max_context_tokens - used_tokens
        if remaining_tokens < 80 or not block.get("truncatable", True):
            dropped.append(
                {
                    "title": block["title"],
                    "source": block["source"],
                    "reason": "budget",
                }
            )
            continue

        header = _render_block({**block, "content": ""})
        available_chars = max(0, (remaining_tokens * 4) - len(header) - 12)
        if available_chars < 120:
            dropped.append(
                {
                    "title": block["title"],
                    "source": block["source"],
                    "reason": "budget",
                }
            )
            continue

        clipped_content = _clip_text(block["content"], available_chars)
        if not clipped_content:
            dropped.append(
                {
                    "title": block["title"],
                    "source": block["source"],
                    "reason": "budget",
                }
            )
            continue

        block["content"] = clipped_content
        block["truncated"] = clipped_content != raw_block["content"]
        rendered = _render_block(block)
        token_estimate = _estimate_tokens(rendered)
        if used_tokens + token_estimate > max_context_tokens:
            dropped.append(
                {
                    "title": block["title"],
                    "source": block["source"],
                    "reason": "budget",
                }
            )
            continue

        block["id"] = f"ctx_{len(selected) + 1:02d}"
        block["token_estimate"] = token_estimate
        block.pop("truncatable", None)
        selected.append(block)
        used_tokens += token_estimate

    return selected, dropped, used_tokens


def _clamp_budget(max_context_tokens: int) -> int:
    """Keep the requested budget within safe server-side limits."""
    return max(_MIN_CONTEXT_TOKENS, min(max_context_tokens, _MAX_CONTEXT_TOKENS))


def _error_json(message: str) -> str:
    """Return a stable JSON error response."""
    return json.dumps({"status": "error", "message": message}, ensure_ascii=False)


def _sync_prepare_llm_payload(
    user_input: str,
    workspace_path: str,
    workspace_id: str,
    tech_stack: str | None,
    max_context_tokens: int,
    memory_scope: str = "workspace",
    agent_id: str = "",
    session_id: str = "",
    session_namespace: str | None = None,
) -> str:
    """Build a compact LLM-ready payload from workspace knowledge and memory."""
    target = Path(workspace_path).expanduser().resolve()
    if not target.exists():
        return _error_json(f"Path does not exist: {target}")
    if not target.is_dir():
        return _error_json(f"Not a directory: {target}")

    applied_budget = _clamp_budget(max_context_tokens or _DEFAULT_CONTEXT_TOKENS)
    normalized_goal = _clip_text(re.sub(r"\s+", " ", user_input).strip(), 240)
    intent = _normalize_intent(user_input)
    signal_terms = _extract_signal_terms(user_input)

    workspace_meta, workspace_blocks = _build_workspace_blocks(target, tech_stack)
    memory_blocks, memory_status = _fetch_memory_blocks(
        query=user_input,
        workspace_id=workspace_id,
        tech_stack=workspace_meta["tech_stack"]
        if workspace_meta["tech_stack"] != "unknown"
        else None,
        memory_scope=memory_scope,
        session_namespace=session_namespace,
    )

    blocks = [
        _build_block(
            kind="task",
            title="Normalized task",
            content=(
                f"User goal: {normalized_goal or 'No user goal provided.'}\n"
                f"Intent: {intent}\n"
                f"Signal terms: {', '.join(signal_terms) if signal_terms else 'none'}\n"
                f"Memory scope: {memory_scope}"
            ),
            source="user_input",
            priority=1.0,
            trust="high",
            truncatable=False,
        )
    ]
    blocks.extend(workspace_blocks)
    blocks.extend(memory_blocks)

    selected_blocks, dropped_blocks, used_tokens = _fit_blocks_to_budget(
        blocks, applied_budget
    )
    compiled_context = "\n\n".join(_render_block(block) for block in selected_blocks)

    return json.dumps(
        {
            "status": "success",
            "schema_version": _SCHEMA_VERSION,
            "task": {
                "user_goal": normalized_goal,
                "normalized_intent": intent,
                "signal_terms": signal_terms,
            },
            "workspace": {
                "path": workspace_meta["path"],
                "id": workspace_id,
                "tech_stack": workspace_meta["tech_stack"],
                "detected_stack": workspace_meta["detected_stack"],
                "detection_method": workspace_meta["detection_method"],
                "confidence": workspace_meta["confidence"],
            },
            "session": {
                "agent_id": agent_id,
                "session_id": session_id,
                "memory_scope": memory_scope,
                "session_namespace": session_namespace or "",
            },
            "budget": {
                "requested_context_tokens": max_context_tokens,
                "applied_context_tokens": applied_budget,
                "used_context_tokens": used_tokens,
                "remaining_context_tokens": max(applied_budget - used_tokens, 0),
            },
            "sources": {
                "memory_status": memory_status,
                "available_references": workspace_meta["available_references"],
                "blocks_generated": len(blocks),
                "blocks_selected": len(selected_blocks),
                "blocks_dropped": len(dropped_blocks),
            },
            "context_blocks": selected_blocks,
            "compiled_context": compiled_context,
            "omitted_blocks": dropped_blocks,
            "usage_guidance": [
                "Use compiled_context as the primary MCP-derived context for the next LLM call.",
                "Avoid chaining auto_recall, analyze_workspace, and search_memory unless a required detail is missing.",
                "If more detail is needed, fetch only the specific source named in context_blocks.",
            ],
        },
        indent=2,
        ensure_ascii=False,
    )


async def prepare_payload_bundle(
    user_input: str,
    workspace_path: str,
    workspace_id: str,
    tech_stack: str | None = None,
    max_context_tokens: int = _DEFAULT_CONTEXT_TOKENS,
    memory_scope: str = "workspace",
    agent_id: str = "",
    session_id: str = "",
    session_namespace: str | None = None,
) -> str:
    """Async facade for prepare_llm_payload."""
    mgr = _get_mgr()
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                mgr._refinery_executor,
                lambda: _sync_prepare_llm_payload(
                    user_input=user_input,
                    workspace_path=workspace_path,
                    workspace_id=workspace_id,
                    tech_stack=tech_stack,
                    max_context_tokens=max_context_tokens,
                    memory_scope=memory_scope,
                    agent_id=agent_id,
                    session_id=session_id,
                    session_namespace=session_namespace,
                ),
            ),
            timeout=_ASYNC_TIMEOUT,
        )
    except asyncio.TimeoutError:
        mgr.reset()
        return _error_json(
            f"prepare_llm_payload timed out after {_ASYNC_TIMEOUT}s."
        )
