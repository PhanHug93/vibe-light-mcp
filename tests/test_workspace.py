"""Tests for workspace isolation — _make_workspace_id validation."""

from __future__ import annotations

import json
import pytest


def test_make_workspace_id_returns_hash() -> None:
    """A valid path should return an 8-char hex hash."""
    from src.server import _make_workspace_id

    ws_id = _make_workspace_id("/Users/admin/projects/my-app")
    assert isinstance(ws_id, str)
    assert len(ws_id) == 8
    assert all(c in "0123456789abcdef" for c in ws_id)


def test_make_workspace_id_deterministic() -> None:
    """Same path must always produce same ID."""
    from src.server import _make_workspace_id

    id1 = _make_workspace_id("/foo/bar")
    id2 = _make_workspace_id("/foo/bar")
    assert id1 == id2


def test_make_workspace_id_different_paths() -> None:
    """Different paths must produce different IDs."""
    from src.server import _make_workspace_id

    id1 = _make_workspace_id("/project_a")
    id2 = _make_workspace_id("/project_b")
    assert id1 != id2


def test_make_workspace_id_empty_raises() -> None:
    """Empty workspace_path must raise ValueError."""
    from src.server import _make_workspace_id

    with pytest.raises(ValueError, match="REQUIRED"):
        _make_workspace_id("")


def test_make_workspace_id_whitespace_raises() -> None:
    """Whitespace-only workspace_path must raise ValueError."""
    from src.server import _make_workspace_id

    with pytest.raises(ValueError, match="REQUIRED"):
        _make_workspace_id("   ")
