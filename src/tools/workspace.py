"""Workspace-related MCP tools — analyze_workspace, read_reference.

Extracted from ``server.py`` for SRP compliance.
"""
from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.config import TECH_STACKS_DIR
from src.engine.stack_detector import detect_stack_enhanced, read_knowledge
from src.tools.helpers import validate_path_within, validate_stack_name
from src.utils.usage_tracker import record_tool_call

_TECH_STACKS_DIR: Path = TECH_STACKS_DIR


def register_workspace_tools(mcp: FastMCP) -> None:
    """Register workspace-related tools onto the FastMCP instance."""

    @mcp.tool()
    async def analyze_workspace(project_path: str) -> str:
        """Scan a project directory, detect the tech stack, and return rules & skills.

        Call this tool when user asks to:
        - Analyze, scan, or detect a project's tech stack
        - Get coding rules or skills for a project
        - Understand what technology a project uses

        Uses two-pass detection:
        1. File signature matching (fast: build.gradle.kts, pubspec.yaml, etc.)
        2. Keyword scanning (deep: scans source files for framework patterns)

        Args:
            project_path: Absolute or relative path to the project root.

        Returns:
            JSON string with detected stack, rules, skills, keyword hits,
            confidence score, and available references.
        """
        target = Path(project_path).expanduser().resolve()

        if not target.exists():
            return json.dumps(
                {"status": "error", "message": f"Path does not exist: {target}"},
                indent=2, ensure_ascii=False,
            )

        if not target.is_dir():
            return json.dumps(
                {"status": "error", "message": f"Not a directory: {target}"},
                indent=2, ensure_ascii=False,
            )

        detection = detect_stack_enhanced(target, _TECH_STACKS_DIR)
        stack = detection["stack"]

        if stack is None:
            return json.dumps(
                {
                    "status": "unknown",
                    "message": "No recognised tech stack found.",
                    "scanned_path": str(target),
                    "hint": "Supported: build.gradle(.kts), pubspec.yaml, package.json",
                },
                indent=2, ensure_ascii=False,
            )

        knowledge = read_knowledge(stack, _TECH_STACKS_DIR)
        record_tool_call("analyze_workspace", stack=stack)

        return json.dumps(
            {
                "status": "success",
                "detected_stack": stack,
                "detection_method": detection["method"],
                "confidence": detection["confidence"],
                "keyword_hits": detection["keyword_hits"],
                "project_path": str(target),
                "rules": knowledge.get("rules.md", ""),
                "skills": knowledge.get("skills.md", ""),
                "available_references": knowledge.get("available_references", []),
            },
            indent=2, ensure_ascii=False,
        )

    @mcp.tool()
    async def read_reference(stack: str, reference_name: str) -> str:
        """Read a detailed reference document from a tech stack's references/ directory.

        Call this tool when user asks to:
        - See detailed examples for a specific topic (e.g. architecture, compose)
        - Deep dive into a reference document
        - Get heavy implementation examples beyond core rules

        Only loads content on demand to save context window.
        Use analyze_workspace first to see available_references.

        Args:
            stack: Tech stack key (e.g. android_kotlin, flutter_dart).
            reference_name: Filename of the reference (e.g. architecture.md).

        Returns:
            JSON with reference content or error message.
        """
        # Security: validate stack name (no traversal via stack param)
        stack_err = validate_stack_name(stack)
        if stack_err:
            return json.dumps(
                {"status": "error", "message": stack_err},
                indent=2, ensure_ascii=False,
            )

        refs_dir = _TECH_STACKS_DIR / stack / "references"

        if not refs_dir.is_dir():
            return json.dumps(
                {"status": "error", "message": f"No references/ directory for stack '{stack}'."},
                indent=2, ensure_ascii=False,
            )

        if not reference_name.endswith(".md"):
            reference_name += ".md"

        # Security: validate resolved path stays within refs_dir
        try:
            ref_path = validate_path_within(refs_dir / reference_name, refs_dir)
        except ValueError as exc:
            return json.dumps(
                {"status": "error", "message": str(exc)},
                indent=2, ensure_ascii=False,
            )
        if not ref_path.is_file():
            available = [f.name for f in refs_dir.iterdir() if f.is_file() and f.suffix == ".md"]
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Reference '{reference_name}' not found.",
                    "available_references": available,
                },
                indent=2, ensure_ascii=False,
            )

        content = ref_path.read_text(encoding="utf-8")
        record_tool_call("read_reference", stack=stack)

        return json.dumps(
            {
                "status": "success",
                "stack": stack,
                "reference": reference_name,
                "content": content,
            },
            indent=2, ensure_ascii=False,
        )
