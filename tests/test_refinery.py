"""Tests for the LLM payload refinery."""

from __future__ import annotations

import concurrent.futures
import json

from src.engine import refinery


class _FakeCollection:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def count(self) -> int:
        return len(self._rows)

    def query(self, query_texts, n_results: int, where=None):  # noqa: ANN001, ARG002
        rows = list(self._rows)
        if where:
            rows = [
                row
                for row in rows
                if all(row.get("metadata", {}).get(k) == v for k, v in where.items())
            ]
        rows.sort(key=lambda row: row.get("distance", 999.0))
        rows = rows[:n_results]
        return {
            "documents": [[row.get("document", "") for row in rows]],
            "metadatas": [[row.get("metadata", {}) for row in rows]],
            "distances": [[row.get("distance", 999.0) for row in rows]],
        }


class _FakeRefineryManager:
    def __init__(
        self,
        *,
        session_rows: list[dict],
        l1_rows: list[dict],
        l2_rows: list[dict],
    ) -> None:
        self._session_collection = _FakeCollection(session_rows)
        self._l1_collection = _FakeCollection(l1_rows)
        self._l2_collection = _FakeCollection(l2_rows)
        self._query_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

    def connect(self):
        return None

    def reset(self) -> None:
        return None

    def get_session_direct(self, session_namespace: str):  # noqa: ARG002
        return self._session_collection

    def get_l1_direct(self, workspace_id: str):  # noqa: ARG002
        return self._l1_collection

    def get_l2_direct(self):
        return self._l2_collection

    def shutdown(self) -> None:
        self._query_executor.shutdown(wait=True)


def test_normalize_intent_detects_architecture_upgrade() -> None:
    """Architecture-oriented requests should be classified deterministically."""
    intent = refinery._normalize_intent(
        "Upgrade this MCP into a gateway that prepares LLM payload tokens."
    )
    assert intent == "architecture_upgrade"


def test_summarize_markdown_prefers_headings_and_bullets() -> None:
    """Markdown summaries should keep high-signal structure, not full prose."""
    content = """# Rules

## Safety
- Validate input
- Enforce budgets

Paragraph that should not dominate the summary.

## Output
1. Return JSON
2. Keep source attribution
"""
    summary = refinery._summarize_markdown(content, max_lines=6, max_chars=220)
    assert "Section: Rules" in summary
    assert "Validate input" in summary
    assert "Return JSON" in summary
    assert len(summary) <= 220


def test_fit_blocks_to_budget_drops_low_priority_blocks() -> None:
    """Budgeting should keep the most important blocks first."""
    blocks = [
        refinery._build_block(
            kind="task",
            title="Task",
            content="Short goal",
            source="user_input",
            priority=1.0,
            trust="high",
            truncatable=False,
        ),
        refinery._build_block(
            kind="knowledge",
            title="Large block",
            content="alpha " * 900,
            source="rules",
            priority=0.2,
            trust="high",
        ),
    ]

    selected, dropped, used = refinery._fit_blocks_to_budget(blocks, max_context_tokens=60)
    assert selected
    assert selected[0]["title"] == "Task"
    assert dropped
    assert used <= 120


def test_sync_prepare_llm_payload_returns_structured_payload(
    tmp_path, monkeypatch
) -> None:
    """The end-to-end sync builder should return a compact payload contract."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    def _fake_memory(*args, **kwargs):
        return (
            [
                refinery._build_block(
                    kind="memory",
                    title="Recent memory",
                    content="Previous design decision about context budgeting.",
                    source="L1_LOCAL",
                    priority=0.9,
                    trust="high",
                )
            ],
            "ready",
        )

    monkeypatch.setattr(refinery, "_fetch_memory_blocks", _fake_memory)

    raw = refinery._sync_prepare_llm_payload(
        user_input="Prepare a compact MCP gateway payload for the next LLM call.",
        workspace_path=str(tmp_path),
        workspace_id="deadbeef",
        tech_stack=None,
        max_context_tokens=700,
    )
    payload = json.loads(raw)

    assert payload["status"] == "success"
    assert payload["schema_version"] == "llm-payload/v1"
    assert payload["workspace"]["tech_stack"] == "python"
    assert payload["sources"]["memory_status"] == "ready"
    assert payload["budget"]["used_context_tokens"] <= payload["budget"]["applied_context_tokens"]
    assert payload["compiled_context"]
    assert any(block["kind"] == "memory" for block in payload["context_blocks"])


def test_sync_prepare_llm_payload_includes_session_scope_metadata(
    tmp_path, monkeypatch
) -> None:
    """Session-scoped requests should surface agent/session metadata in payload."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    monkeypatch.setattr(refinery, "_fetch_memory_blocks", lambda *args, **kwargs: ([], "empty"))

    raw = refinery._sync_prepare_llm_payload(
        user_input="Prepare context for agent beta.",
        workspace_path=str(tmp_path),
        workspace_id="deadbeef",
        tech_stack=None,
        max_context_tokens=700,
        memory_scope="session",
        agent_id="agent-beta",
        session_id="turn-42",
        session_namespace="abc123session",
    )
    payload = json.loads(raw)

    assert payload["status"] == "success"
    assert payload["session"]["memory_scope"] == "session"
    assert payload["session"]["agent_id"] == "agent-beta"
    assert payload["session"]["session_id"] == "turn-42"
    assert payload["session"]["session_namespace"] == "abc123session"


def test_collect_memory_hits_session_scope_reads_session_l1_l2(monkeypatch) -> None:
    """Session retrieval should read SESSION_LOCAL + L1_LOCAL + L2_GLOBAL."""
    mgr = _FakeRefineryManager(
        session_rows=[
            {
                "document": "session note",
                "metadata": {"source": "session", "tech_stack": "legacy"},
                "distance": 0.23,
            }
        ],
        l1_rows=[
            {
                "document": "workspace note",
                "metadata": {"source": "workspace", "tech_stack": "legacy"},
                "distance": 0.24,
            }
        ],
        l2_rows=[
            {
                "document": "global note",
                "metadata": {"source": "global", "tech_stack": "python"},
                "distance": 0.2,
            }
        ],
    )
    monkeypatch.setattr(refinery, "_get_mgr", lambda: mgr)
    try:
        hits = refinery._collect_memory_hits(
            query="prepare payload",
            workspace_id="deadbeef",
            tech_stack="python",
            max_items=10,
            memory_scope="session",
            session_namespace="abc123",
        )
    finally:
        mgr.shutdown()

    tiers = {item["tier"] for item in hits}
    assert "SESSION_LOCAL" in tiers
    assert "L1_LOCAL" in tiers
    assert "L2_GLOBAL" in tiers


def test_collect_memory_hits_keeps_local_even_when_l2_matches_stack(monkeypatch) -> None:
    """Local session/workspace hits must not be hidden by L2 stack-filter hits."""
    mgr = _FakeRefineryManager(
        session_rows=[
            {
                "document": "session mismatch stack",
                "metadata": {"source": "session", "tech_stack": "kotlin"},
                "distance": 0.22,
            }
        ],
        l1_rows=[
            {
                "document": "workspace mismatch stack",
                "metadata": {"source": "workspace", "tech_stack": "kotlin"},
                "distance": 0.25,
            }
        ],
        l2_rows=[
            {
                "document": "global matching stack",
                "metadata": {"source": "global", "tech_stack": "python"},
                "distance": 0.2,
            }
        ],
    )
    monkeypatch.setattr(refinery, "_get_mgr", lambda: mgr)
    try:
        hits = refinery._collect_memory_hits(
            query="prepare payload",
            workspace_id="deadbeef",
            tech_stack="python",
            max_items=10,
            memory_scope="session",
            session_namespace="abc123",
        )
    finally:
        mgr.shutdown()

    tiers = [item["tier"] for item in hits]
    assert "SESSION_LOCAL" in tiers
    assert "L1_LOCAL" in tiers
    assert "L2_GLOBAL" in tiers


def test_collect_memory_hits_near_tie_prefers_local_scope(monkeypatch) -> None:
    """Near-tie ranking should prefer session, then workspace, over global."""
    mgr = _FakeRefineryManager(
        session_rows=[
            {
                "document": "session close relevance",
                "metadata": {"source": "session", "tech_stack": "python"},
                "distance": 0.22,
            }
        ],
        l1_rows=[
            {
                "document": "workspace close relevance",
                "metadata": {"source": "workspace", "tech_stack": "python"},
                "distance": 0.21,
            }
        ],
        l2_rows=[
            {
                "document": "global close relevance",
                "metadata": {"source": "global", "tech_stack": "python"},
                "distance": 0.2,
            }
        ],
    )
    monkeypatch.setattr(refinery, "_get_mgr", lambda: mgr)
    try:
        hits = refinery._collect_memory_hits(
            query="prepare payload",
            workspace_id="deadbeef",
            tech_stack="python",
            max_items=3,
            memory_scope="session",
            session_namespace="abc123",
        )
    finally:
        mgr.shutdown()

    assert [item["tier"] for item in hits] == ["SESSION_LOCAL", "L1_LOCAL", "L2_GLOBAL"]


def test_collect_memory_hits_large_gap_keeps_l2_first(monkeypatch) -> None:
    """Large relevance gaps must not be inverted by local-tier bonus."""
    mgr = _FakeRefineryManager(
        session_rows=[
            {
                "document": "session weak relevance",
                "metadata": {"source": "session", "tech_stack": "python"},
                "distance": 0.56,
            }
        ],
        l1_rows=[
            {
                "document": "workspace weak relevance",
                "metadata": {"source": "workspace", "tech_stack": "python"},
                "distance": 0.5,
            }
        ],
        l2_rows=[
            {
                "document": "global very relevant",
                "metadata": {"source": "global", "tech_stack": "python"},
                "distance": 0.12,
            }
        ],
    )
    monkeypatch.setattr(refinery, "_get_mgr", lambda: mgr)
    try:
        hits = refinery._collect_memory_hits(
            query="prepare payload",
            workspace_id="deadbeef",
            tech_stack="python",
            max_items=3,
            memory_scope="session",
            session_namespace="abc123",
        )
    finally:
        mgr.shutdown()

    assert hits[0]["tier"] == "L2_GLOBAL"


def test_sync_prepare_llm_payload_session_scope_includes_all_tiers(
    tmp_path, monkeypatch
) -> None:
    """Payload should surface SESSION_LOCAL + L1_LOCAL + L2_GLOBAL blocks."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    mgr = _FakeRefineryManager(
        session_rows=[
            {
                "document": "session memory",
                "metadata": {"source": "session-source", "tech_stack": "legacy"},
                "distance": 0.22,
            }
        ],
        l1_rows=[
            {
                "document": "workspace memory",
                "metadata": {"source": "workspace-source", "tech_stack": "legacy"},
                "distance": 0.24,
            }
        ],
        l2_rows=[
            {
                "document": "global memory",
                "metadata": {"source": "global-source", "tech_stack": "python"},
                "distance": 0.2,
            }
        ],
    )
    monkeypatch.setattr(refinery, "_get_mgr", lambda: mgr)
    try:
        raw = refinery._sync_prepare_llm_payload(
            user_input="Prepare context bundle for session agent.",
            workspace_path=str(tmp_path),
            workspace_id="deadbeef",
            tech_stack="python",
            max_context_tokens=2000,
            memory_scope="session",
            agent_id="agent-a",
            session_id="current",
            session_namespace="abc123session",
        )
    finally:
        mgr.shutdown()

    payload = json.loads(raw)
    memory_sources = {
        block["source"]
        for block in payload["context_blocks"]
        if block["kind"] == "memory"
    }
    assert "SESSION_LOCAL" in memory_sources
    assert "L1_LOCAL" in memory_sources
    assert "L2_GLOBAL" in memory_sources
    assert "SESSION_LOCAL memory from session-source" in payload["compiled_context"]
    assert "L1_LOCAL memory from workspace-source" in payload["compiled_context"]
    assert "L2_GLOBAL memory from global-source" in payload["compiled_context"]
