"""Tests for context-engine memory-scope topology."""

from __future__ import annotations

from src.engine import context


class _DummyManager:
    def get_l1_direct(self, workspace_id: str):  # noqa: ARG002
        return object()

    def get_session_direct(self, session_namespace: str):  # noqa: ARG002
        return object()

    def get_l2_direct(self):
        return object()


def test_build_query_specs_session_includes_session_l1_l2() -> None:
    """Session scope should read from session-local, workspace-local, and global."""
    mgr = _DummyManager()
    specs = context._build_query_specs(  # noqa: SLF001 - testing internal behavior contract
        mgr,
        workspace_id="deadbeef",
        memory_scope="session",
        session_namespace="abc123",
    )
    labels = [label for label, _ in specs]
    assert labels == ["SESSION_LOCAL", "L1_LOCAL", "L2_GLOBAL"]


def test_build_query_specs_workspace_keeps_l1_l2() -> None:
    """Workspace scope should keep existing L1 + L2 read-through behavior."""
    mgr = _DummyManager()
    specs = context._build_query_specs(  # noqa: SLF001 - testing internal behavior contract
        mgr,
        workspace_id="deadbeef",
        memory_scope="workspace",
    )
    labels = [label for label, _ in specs]
    assert labels == ["L1_LOCAL", "L2_GLOBAL"]
