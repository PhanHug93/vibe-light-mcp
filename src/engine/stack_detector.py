"""Stack Detector — Tech stack auto-detection via file signatures + keyword scan.

Standalone module, no MCP dependency. Extracted from ``server.py`` (SRP).
Stack definitions loaded from ``tech_stacks/registry.yaml`` (Open/Closed).

Usage::

    from src.engine.stack_detector import detect_stack_enhanced, read_knowledge
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registry Loader — reads from YAML config (P7: Open/Closed Principle)
# ---------------------------------------------------------------------------

_SEARCH_DEPTH: int = 1  # root + one level deep
_KEYWORD_SCAN_MAX_FILES: int = 20
_KEYWORD_SCAN_MAX_BYTES: int = 50_000  # per file

# Cache loaded registry
_registry_cache: dict[str, Any] | None = None


def _load_registry(tech_stacks_dir: Path) -> dict[str, Any]:
    """Load stack registry from ``registry.yaml``.

    Requires PyYAML (hard dependency declared in pyproject.toml).
    """
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache

    yaml_path = tech_stacks_dir / "registry.yaml"
    if not yaml_path.exists():
        logger.warning("registry.yaml not found at %s — no stacks configured.", yaml_path)
        _registry_cache = {"signatures": [], "triggers": {}}
        return _registry_cache

    import yaml  # hard dependency (pyyaml>=6.0)

    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        _registry_cache = {
            "signatures": raw.get("signatures", []),
            "triggers": raw.get("triggers", {}),
        }
    except Exception as exc:
        logger.error("Failed to load registry.yaml: %s", exc)
        _registry_cache = {"signatures": [], "triggers": {}}

    return _registry_cache


# ---------------------------------------------------------------------------
# Detection Functions
# ---------------------------------------------------------------------------


def _detect_by_signature(project_path: Path, signatures: list[dict[str, str]]) -> str | None:
    """Scan *project_path* for signature files and return the stack key."""
    for depth in range(_SEARCH_DEPTH + 1):
        search_dirs: list[Path] = (
            [project_path] if depth == 0
            else [d for d in project_path.iterdir() if d.is_dir()]
        )
        for directory in search_dirs:
            for entry in signatures:
                if (directory / entry["file"]).exists():
                    return entry["stack"]
    return None


def _scan_keywords(
    project_path: Path,
    stack: str,
    all_triggers: dict[str, dict[str, list[str]]],
) -> dict[str, int]:
    """Scan source files for keyword hits. Returns {keyword: count}."""
    triggers = all_triggers.get(stack)
    if not triggers:
        return {}

    extensions = set(triggers.get("extensions", []))
    keywords = triggers.get("keywords", [])
    hits: dict[str, int] = {}
    files_scanned = 0

    for source_file in project_path.rglob("*"):
        if files_scanned >= _KEYWORD_SCAN_MAX_FILES:
            break
        if not source_file.is_file():
            continue
        if source_file.suffix not in extensions:
            continue
        # Skip hidden dirs, build dirs, etc.
        parts = source_file.relative_to(project_path).parts
        if any(p.startswith(".") or p in ("build", "node_modules", ".gradle") for p in parts):
            continue

        try:
            content = source_file.read_text(encoding="utf-8", errors="ignore")
            if len(content) > _KEYWORD_SCAN_MAX_BYTES:
                content = content[:_KEYWORD_SCAN_MAX_BYTES]
        except (OSError, UnicodeDecodeError):
            continue

        files_scanned += 1
        for kw in keywords:
            count = content.count(kw)
            if count > 0:
                hits[kw] = hits.get(kw, 0) + count

    return hits


def detect_stack_enhanced(project_path: Path, tech_stacks_dir: Path | None = None) -> dict:
    """Enhanced detection: file signature + keyword scan.

    Args:
        project_path: The project directory to analyze.
        tech_stacks_dir: Path to tech_stacks/ (for loading registry.yaml).
            If None, uses config default.

    Returns:
        dict with: stack, method, keyword_hits, confidence.
    """
    if tech_stacks_dir is None:
        from src.config import TECH_STACKS_DIR
        tech_stacks_dir = TECH_STACKS_DIR

    registry = _load_registry(tech_stacks_dir)
    signatures = registry["signatures"]
    all_triggers = registry["triggers"]

    stack = _detect_by_signature(project_path, signatures)
    method = "file_signature" if stack else "none"

    if stack is None:
        # Fallback: try keyword-only detection across all stacks
        best_stack = None
        best_score = 0
        for candidate_stack in all_triggers:
            hits = _scan_keywords(project_path, candidate_stack, all_triggers)
            score = sum(hits.values())
            if score > best_score:
                best_score = score
                best_stack = candidate_stack
        if best_stack and best_score >= 3:
            stack = best_stack
            method = "keyword_only"

    # Keyword scan for matched stack
    keyword_hits: dict[str, int] = {}
    confidence = 0.0
    if stack:
        keyword_hits = _scan_keywords(project_path, stack, all_triggers)
        unique_keywords = len(keyword_hits)

        if method == "file_signature":
            confidence = min(0.7 + (unique_keywords * 0.05), 1.0)
        else:
            confidence = min(0.3 + (unique_keywords * 0.07), 0.9)

        if method == "file_signature" and keyword_hits:
            method = "file_signature + keyword_scan"

    return {
        "stack": stack,
        "method": method,
        "keyword_hits": keyword_hits,
        "confidence": round(confidence, 2),
    }


# ---------------------------------------------------------------------------
# Knowledge Reader
# ---------------------------------------------------------------------------


def read_knowledge(stack: str, tech_stacks_dir: Path) -> dict:
    """Read core rules/skills + list available references for *stack*.

    Args:
        stack: The tech stack key (e.g. ``android_kotlin``).
        tech_stacks_dir: Absolute path to the ``tech_stacks/`` directory.
    """
    stack_dir: Path = tech_stacks_dir / stack
    result: dict[str, str | list[str]] = {}

    # Core files (always loaded)
    for filename in ("rules.md", "skills.md"):
        filepath: Path = stack_dir / filename
        try:
            result[filename] = filepath.read_text(encoding="utf-8")
        except FileNotFoundError:
            result[filename] = f"⚠ {filepath} not found."

    # Progressive disclosure: list references (loaded on demand)
    refs_dir = stack_dir / "references"
    if refs_dir.is_dir():
        result["available_references"] = sorted(
            f.name for f in refs_dir.iterdir()
            if f.is_file() and f.suffix == ".md"
        )
    else:
        result["available_references"] = []

    return result
