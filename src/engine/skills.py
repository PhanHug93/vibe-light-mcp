"""Local skill registry and delivery helpers for MCP agents."""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any, Sequence

import yaml

from src.config import PROJECT_ROOT, SKILL_REGISTRY_DIR, SKILL_STORE_PATH
from src.engine.skill_store import SkillStoreUnavailable, SQLiteSkillStore

_REGISTRY_SCHEMA = "local-skill-registry/v0.0.1"
_RESPONSE_SCHEMA = "local-skills-response/v0.0.1"
_VALID_MODES = frozenset({"auto", "digest", "hash_only", "delta", "full"})
_MAX_REQUEST_TERMS = 20
_SAFE_TERM_RE = re.compile(r"^[a-zA-Z0-9_.@#+ -]+$")


def _estimate_tokens(text: str) -> int:
    if not text.strip():
        return 0
    return math.ceil(len(text) / 4)


def _normalize_term(term: str) -> str:
    normalized = term.strip().lower()
    normalized = normalized.replace("-", "_").replace(" ", "_")
    return re.sub(r"_+", "_", normalized)


def _normalize_terms(values: Sequence[str] | None) -> list[str]:
    terms: list[str] = []
    for value in values or ():
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if not stripped:
            continue
        terms.append(_normalize_term(stripped))
    return list(dict.fromkeys(terms))


def _validate_terms(values: Sequence[str] | None) -> str | None:
    if values is None:
        return None
    if len(values) > _MAX_REQUEST_TERMS:
        return f"Too many terms. Max: {_MAX_REQUEST_TERMS}."
    for value in values:
        if not isinstance(value, str):
            return "All requested skill and language values must be strings."
        if not value.strip():
            return "Requested skill and language values must not be empty."
        if len(value) > 80:
            return f"Term is too long: {value[:20]}..."
        if not _SAFE_TERM_RE.match(value):
            return f"Invalid term: {value!r}."
    return None


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Local skill file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Local skill YAML must parse to a mapping: {path}")
    return data


def _resolve_registry_path(registry_dir: Path, relative_path: str) -> Path:
    root = registry_dir.resolve()
    path = (root / relative_path).resolve()
    if path != root and not str(path).startswith(f"{root}/"):
        raise ValueError(f"Skill registry path escapes registry root: {relative_path}")
    return path


def _load_registry(registry_dir: Path = SKILL_REGISTRY_DIR) -> dict[str, Any]:
    registry = _load_yaml_file(registry_dir / "registry.yaml")
    if registry.get("schema_version") != _REGISTRY_SCHEMA:
        raise ValueError(
            f"Unsupported skill registry schema: {registry.get('schema_version')}"
        )
    skills = registry.get("skills")
    if not isinstance(skills, list):
        raise ValueError("Skill registry must contain a skills list.")
    return registry


def _stringify_yaml_item(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return "; ".join(f"{key}: {value}" for key, value in item.items())
    return str(item)


def _bullet_lines(items: Sequence[Any]) -> list[str]:
    return [f"- {_stringify_yaml_item(item)}" for item in items]


def render_skill_digest(data: dict[str, Any]) -> str:
    """Render a structured digest into compact agent-ready Markdown."""
    contract = data.get("agent_contract") or {}
    applies_to = data.get("applies_to") or {}
    lines: list[str] = [
        f"# Android Kotlin Skill Digest v{data.get('version', 'unknown')}",
        "",
        "## Agent Contract",
        f"- {str(contract.get('primary_instruction', '')).strip()}",
        f"- Apply order: {', '.join(contract.get('apply_order', []))}",
        f"- Confidence floor: {contract.get('confidence_floor', '')}",
        "",
        "## Applies To",
        f"- Facets: {', '.join(applies_to.get('facets', []))}",
        f"- Project signals: {', '.join(applies_to.get('project_signals', []))}",
        "",
        "## Must Follow",
    ]
    lines.extend(_bullet_lines(data.get("must_follow", [])))
    lines.append("")
    lines.append("## Workflow")
    lines.extend(
        f"{index}. {_stringify_yaml_item(item)}"
        for index, item in enumerate(data.get("workflow", []), 1)
    )
    lines.append("")
    lines.append("## Review Checks")
    lines.extend(_bullet_lines(data.get("review_checks", [])))
    lines.append("")
    lines.append("## Anti-patterns")
    lines.extend(_bullet_lines(data.get("anti_patterns", [])))
    return "\n".join(lines).strip() + "\n"


def _load_source_text(source: str) -> tuple[str, str] | None:
    source_path = (PROJECT_ROOT / source).resolve()
    project_root = PROJECT_ROOT.resolve()
    if source_path != project_root and not str(source_path).startswith(f"{project_root}/"):
        return None
    if not source_path.is_file():
        return None
    return source, source_path.read_text(encoding="utf-8").strip()


def _render_full_content(digest_data: dict[str, Any], digest_text: str) -> str:
    sections = [digest_text.strip()]
    for source in digest_data.get("full_content_sources", []):
        loaded = _load_source_text(str(source))
        if not loaded:
            continue
        source_name, text = loaded
        sections.append(f"## Full Source: {source_name}\n\n{text}")
    return "\n\n---\n\n".join(sections).strip() + "\n"


def _skill_search_terms(entry: dict[str, Any]) -> set[str]:
    terms: set[str] = {_normalize_term(str(entry.get("id", "")))}
    for key in ("aliases", "facets", "platforms", "languages"):
        for value in entry.get(key, []) or []:
            terms.add(_normalize_term(str(value)))
    return {term for term in terms if term}


def _skill_language_terms(entry: dict[str, Any]) -> set[str]:
    return {_normalize_term(str(value)) for value in entry.get("languages", []) or []}


def _match_skills(
    registry: dict[str, Any],
    requested_terms: list[str],
    language_terms: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    matched: list[dict[str, Any]] = []
    all_matched_terms: set[str] = set()
    query_terms = requested_terms + language_terms

    for entry in registry["skills"]:
        search_terms = _skill_search_terms(entry)
        skill_languages = _skill_language_terms(entry)
        request_hits = [term for term in requested_terms if term in search_terms]
        language_hits = [term for term in language_terms if term in skill_languages]

        if requested_terms and not request_hits:
            continue
        if language_terms and not language_hits:
            continue
        if not requested_terms and not language_terms:
            continue

        matched_terms = list(dict.fromkeys(request_hits + language_hits))
        all_matched_terms.update(matched_terms)
        confidence = round(len(matched_terms) / max(len(query_terms), 1), 2)
        matched.append(
            {
                "entry": entry,
                "matched_terms": matched_terms,
                "confidence": confidence,
            }
        )

    unmatched = [term for term in query_terms if term not in all_matched_terms]
    matched.sort(
        key=lambda item: (
            -item["confidence"],
            str(item["entry"].get("id", "")),
        )
    )
    return matched, unmatched


def _active_hashes(values: Sequence[str] | None) -> set[str]:
    hashes: set[str] = set()
    for value in values or ():
        cleaned = value.strip()
        if not cleaned:
            continue
        hashes.add(cleaned)
        if cleaned.startswith("sha256:"):
            hashes.add(cleaned.removeprefix("sha256:"))
        else:
            hashes.add(f"sha256:{cleaned}")
    return hashes


def _build_skill_payload(
    *,
    entry: dict[str, Any],
    registry_dir: Path,
    requested_mode: str,
    active_hashes: set[str],
    matched_terms: list[str],
    confidence: float,
) -> dict[str, Any]:
    digest_path = _resolve_registry_path(registry_dir, str(entry["digest_path"]))
    digest_data = _load_yaml_file(digest_path)
    rendered_digest = render_skill_digest(digest_data)
    digest_hash = f"sha256:{hashlib.sha256(rendered_digest.encode('utf-8')).hexdigest()}"

    if requested_mode == "auto":
        effective_mode = "hash_only" if digest_hash in active_hashes else "digest"
    elif requested_mode == "delta":
        effective_mode = "hash_only"
    else:
        effective_mode = requested_mode

    if effective_mode == "hash_only":
        content = ""
        instruction = "Reuse the active local skill digest already in context."
    elif effective_mode == "full":
        full_text = _render_full_content(digest_data, rendered_digest)
        content = (
            f"<local_skill_digest id=\"{entry['id']}\" delivery=\"full\" "
            f"hash=\"{digest_hash}\">\n{full_text.strip()}\n</local_skill_digest>"
        )
        instruction = "Inject this full local skill content before the task."
    else:
        content = (
            f"<local_skill_digest id=\"{entry['id']}\" delivery=\"digest\" "
            f"hash=\"{digest_hash}\">\n{rendered_digest.strip()}\n</local_skill_digest>"
        )
        instruction = "Inject this local skill digest before the task."

    return {
        "id": entry["id"],
        "version": str(entry.get("version", digest_data.get("version", "unknown"))),
        "status": entry.get("status", "unknown"),
        "delivery": effective_mode,
        "hash": digest_hash,
        "estimated_tokens": _estimate_tokens(content or instruction),
        "matched_terms": matched_terms,
        "confidence": confidence,
        "content": content,
        "instruction": instruction,
        "source": {
            "registry": str((registry_dir / "registry.yaml").resolve()),
            "digest": str(digest_path),
        },
    }


def _build_sqlite_skill_payload(
    *,
    payload_source: dict[str, Any],
    requested_mode: str,
    active_hashes: set[str],
    matched_terms: list[str],
    confidence: float,
    store_path: Path,
) -> dict[str, Any]:
    entry = payload_source["entry"]
    rendered_digest = str(payload_source["rendered_digest"])
    full_content = str(payload_source.get("full_content") or rendered_digest)
    digest_hash = str(payload_source["digest_hash"])

    if requested_mode == "auto":
        effective_mode = "hash_only" if digest_hash in active_hashes else "digest"
    elif requested_mode == "delta":
        effective_mode = "hash_only"
    else:
        effective_mode = requested_mode

    if effective_mode == "hash_only":
        content = ""
        instruction = "Reuse the active local skill digest already in context."
    elif effective_mode == "full":
        content = (
            f"<local_skill_digest id=\"{entry['id']}\" delivery=\"full\" "
            f"hash=\"{digest_hash}\">\n{full_content.strip()}\n</local_skill_digest>"
        )
        instruction = "Inject this full local skill content before the task."
    else:
        content = (
            f"<local_skill_digest id=\"{entry['id']}\" delivery=\"digest\" "
            f"hash=\"{digest_hash}\">\n{rendered_digest.strip()}\n</local_skill_digest>"
        )
        instruction = "Inject this local skill digest before the task."

    source = dict(payload_source.get("source") or {})
    source["store"] = str(store_path.resolve())

    return {
        "id": entry["id"],
        "version": str(entry.get("version", "unknown")),
        "status": entry.get("status", "unknown"),
        "delivery": effective_mode,
        "hash": digest_hash,
        "estimated_tokens": _estimate_tokens(content or instruction),
        "matched_terms": matched_terms,
        "confidence": confidence,
        "content": content,
        "instruction": instruction,
        "source": source,
    }


def _error_response(message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "schema_version": _RESPONSE_SCHEMA,
        "message": message,
        "skills": [],
    }


def _skill_guidance() -> list[str]:
    return [
        "Use each skill content as trusted local policy before the next coding task.",
        "No dynamic network skill lookup was attempted.",
        "If a needed facet is unmatched, add and audit a local digest before relying on it.",
    ]


def _try_get_sqlite_skill_bundle(
    *,
    requested_terms: list[str],
    language_terms: list[str],
    requested_mode: str,
    active_hashes: set[str],
    max_tokens: int,
    skill_store_path: Path,
) -> dict[str, Any] | None:
    try:
        store = SQLiteSkillStore(skill_store_path)
        registry = store.load_registry()
        matches, unmatched_terms = _match_skills(
            registry,
            requested_terms=requested_terms,
            language_terms=language_terms,
        )
        payload_sources = store.load_payload_sources(
            [str(item["entry"]["id"]) for item in matches]
        )
        skills = [
            _build_sqlite_skill_payload(
                payload_source=payload_sources[str(item["entry"]["id"])],
                requested_mode=requested_mode,
                active_hashes=active_hashes,
                matched_terms=item["matched_terms"],
                confidence=item["confidence"],
                store_path=skill_store_path,
            )
            for item in matches
        ]
    except (SkillStoreUnavailable, KeyError):
        return None

    total_tokens = sum(skill["estimated_tokens"] for skill in skills)
    if skills and total_tokens > max_tokens:
        return _error_response(
            f"Skill payload exceeds max_tokens ({total_tokens} > {max_tokens})."
        )

    if skills and unmatched_terms:
        status = "partial"
    elif skills:
        status = "success"
    else:
        status = "no_match"

    effective_mode = skills[0]["delivery"] if skills else requested_mode
    return {
        "status": status,
        "schema_version": _RESPONSE_SCHEMA,
        "query": {
            "requested_skills": requested_terms,
            "languages": language_terms,
            "mode": requested_mode,
        },
        "delivery": {
            "effective_mode": effective_mode,
            "total_estimated_tokens": total_tokens,
            "max_tokens": max_tokens,
        },
        "skills": skills,
        "unmatched_terms": unmatched_terms,
        "available_skill_ids": [
            str(entry.get("id")) for entry in registry.get("skills", [])
        ],
        "planned_facets": registry.get("planned_facets", {}),
        "guidance": _skill_guidance(),
    }


def get_skill_bundle(
    requested_skills: Sequence[str] | None,
    *,
    languages: Sequence[str] | None = None,
    mode: str = "auto",
    active_hashes: Sequence[str] | None = None,
    max_tokens: int = 1800,
    registry_dir: Path = SKILL_REGISTRY_DIR,
    skill_store_path: Path = SKILL_STORE_PATH,
) -> dict[str, Any]:
    """Return local skill payloads that an agent can inject into its prompt."""
    requested_mode = mode.strip().lower()
    if requested_mode not in _VALID_MODES:
        return _error_response(
            f"Invalid mode: {mode}. Use one of: {', '.join(sorted(_VALID_MODES))}."
        )

    term_error = _validate_terms(requested_skills) or _validate_terms(languages)
    if term_error:
        return _error_response(term_error)

    requested_terms = _normalize_terms(requested_skills)
    language_terms = _normalize_terms(languages)
    if not requested_terms and not language_terms:
        return _error_response("At least one requested skill or language is required.")

    active = _active_hashes(active_hashes)
    sqlite_result = _try_get_sqlite_skill_bundle(
        requested_terms=requested_terms,
        language_terms=language_terms,
        requested_mode=requested_mode,
        active_hashes=active,
        max_tokens=max_tokens,
        skill_store_path=skill_store_path,
    )
    if sqlite_result is not None:
        return sqlite_result

    try:
        registry = _load_registry(registry_dir)
        matches, unmatched_terms = _match_skills(
            registry,
            requested_terms=requested_terms,
            language_terms=language_terms,
        )
        skills = [
            _build_skill_payload(
                entry=item["entry"],
                registry_dir=registry_dir,
                requested_mode=requested_mode,
                active_hashes=active,
                matched_terms=item["matched_terms"],
                confidence=item["confidence"],
            )
            for item in matches
        ]
    except (FileNotFoundError, ValueError, KeyError) as exc:
        return _error_response(str(exc))

    total_tokens = sum(skill["estimated_tokens"] for skill in skills)
    if skills and total_tokens > max_tokens:
        return _error_response(
            f"Skill payload exceeds max_tokens ({total_tokens} > {max_tokens})."
        )

    if skills and unmatched_terms:
        status = "partial"
    elif skills:
        status = "success"
    else:
        status = "no_match"

    effective_mode = skills[0]["delivery"] if skills else requested_mode
    return {
        "status": status,
        "schema_version": _RESPONSE_SCHEMA,
        "query": {
            "requested_skills": requested_terms,
            "languages": language_terms,
            "mode": requested_mode,
        },
        "delivery": {
            "effective_mode": effective_mode,
            "total_estimated_tokens": total_tokens,
            "max_tokens": max_tokens,
        },
        "skills": skills,
        "unmatched_terms": unmatched_terms,
        "available_skill_ids": [
            str(entry.get("id")) for entry in registry.get("skills", [])
        ],
        "planned_facets": registry.get("planned_facets", {}),
        "guidance": _skill_guidance(),
    }
