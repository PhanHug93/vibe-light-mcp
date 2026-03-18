"""Knowledge-related MCP tools — sync, update_tech_stack, usage_stats.

Extracted from ``server.py`` for SRP compliance.
"""
from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.config import PROJECT_ROOT, TECH_STACKS_DIR
from src.engine.knowledge import sync_knowledge_from_git
from src.tools.helpers import validate_path_within, validate_stack_name
from src.utils.markdown_utils import parse_md_sections, merge_md_sections, replace_md_section
from src.utils.usage_tracker import record_tool_call, get_daily_stats


def register_knowledge_tools(mcp: FastMCP) -> None:
    """Register knowledge-related tools onto the FastMCP instance."""

    @mcp.tool()
    async def sync_knowledge(repo_url: str) -> str:
        """Sync the local tech_stacks/ knowledge base from a remote Git repository.

        Call this tool when user asks to:
        - Update, sync, or refresh the knowledge base / rules / skills
        - Pull latest tech stack rules from a Git repo
        - Import or download coding standards

        Args:
            repo_url: HTTPS or SSH URL of the Git repository containing
                the tech_stacks content (rules.md, skills.md).

        Returns:
            JSON report with sync status (clone / pull / force_reset / error).
        """
        result = await sync_knowledge_from_git(repo_url)
        record_tool_call("sync_knowledge", query=repo_url)
        return result

    @mcp.tool()
    async def update_tech_stack(
        stack: str,
        target_file: str,
        new_content: str,
        mode: str = "append",
        section_header: str = "",
    ) -> str:
        """Update a tech stack knowledge file with merge support (no data loss).

        Call this tool when user asks to:
        - Add new rules, skills, or references to an existing tech stack
        - Update a specific section of rules or skills
        - Extend the knowledge base with additional content

        Three modes:
        - ``append``          — Add new sections to end of file, skip duplicates
        - ``replace_section`` — Replace a specific ## section (requires section_header)
        - ``overwrite``       — Replace entire file content (use with caution)

        Args:
            stack: Tech stack key (e.g. python, android_kotlin, flutter_dart).
            target_file: One of "rules", "skills", or a reference filename
                (e.g. "testing" → references/testing.md).
            new_content: The markdown content to add or replace.
            mode: Update mode — "append" (default), "replace_section", "overwrite".
            section_header: Required for replace_section mode.
                The H2 header text to replace (without "## " prefix).

        Returns:
            JSON with update status, sections added/skipped (append mode),
            or replacement result (replace_section mode).
        """
        # Security: validate stack name
        stack_err = validate_stack_name(stack)
        if stack_err:
            return json.dumps({
                "status": "error", "message": stack_err,
            }, indent=2, ensure_ascii=False)

        stack_dir = TECH_STACKS_DIR / stack

        # Resolve target file path
        if target_file in ("rules", "rules.md"):
            target_path = stack_dir / "rules.md"
        elif target_file in ("skills", "skills.md"):
            target_path = stack_dir / "skills.md"
        else:
            ref_name = target_file if target_file.endswith(".md") else f"{target_file}.md"
            target_path = stack_dir / "references" / ref_name

        # Security: validate resolved path stays within TECH_STACKS_DIR
        try:
            target_path = validate_path_within(target_path, TECH_STACKS_DIR)
        except ValueError as exc:
            return json.dumps({
                "status": "error", "message": str(exc),
            }, indent=2, ensure_ascii=False)

        # Validate mode
        valid_modes = ("append", "replace_section", "overwrite")
        if mode not in valid_modes:
            return json.dumps({
                "status": "error",
                "message": f"Invalid mode: '{mode}'. Use one of: {valid_modes}",
            }, indent=2, ensure_ascii=False)

        if mode == "replace_section" and not section_header:
            return json.dumps({
                "status": "error",
                "message": "section_header is required for replace_section mode.",
            }, indent=2, ensure_ascii=False)

        # Ensure parent directories exist
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Read existing content
        existing_content = ""
        if target_path.is_file():
            existing_content = target_path.read_text(encoding="utf-8")

        # Mode: overwrite
        if mode == "overwrite":
            target_path.write_text(new_content, encoding="utf-8")
            record_tool_call("update_tech_stack", stack=stack)
            return json.dumps({
                "status": "success",
                "mode": "overwrite",
                "stack": stack,
                "file": str(target_path.relative_to(PROJECT_ROOT)),
                "size": len(new_content),
                "message": "File overwritten completely.",
            }, indent=2, ensure_ascii=False)

        # Mode: append (with dedup)
        if mode == "append":
            if not existing_content:
                target_path.write_text(new_content, encoding="utf-8")
                record_tool_call("update_tech_stack", stack=stack)
                return json.dumps({
                    "status": "success",
                    "mode": "append",
                    "stack": stack,
                    "file": str(target_path.relative_to(PROJECT_ROOT)),
                    "message": "New file created (no existing content).",
                    "size": len(new_content),
                }, indent=2, ensure_ascii=False)

            merged, added, skipped = merge_md_sections(existing_content, new_content)
            target_path.write_text(merged, encoding="utf-8")
            record_tool_call("update_tech_stack", stack=stack)
            return json.dumps({
                "status": "success",
                "mode": "append",
                "stack": stack,
                "file": str(target_path.relative_to(PROJECT_ROOT)),
                "sections_added": added,
                "sections_skipped_duplicate": skipped,
                "message": (
                    f"Added {len(added)} new section(s), "
                    f"skipped {len(skipped)} duplicate(s)."
                ),
            }, indent=2, ensure_ascii=False)

        # Mode: replace_section
        if mode == "replace_section":
            if not existing_content:
                return json.dumps({
                    "status": "error",
                    "message": "File does not exist yet. Use 'append' mode to create it first.",
                }, indent=2, ensure_ascii=False)

            updated, found = replace_md_section(
                existing_content, section_header, new_content,
            )
            if not found:
                sections = parse_md_sections(existing_content)
                available = [h for h in sections if h != "__preamble__"]
                return json.dumps({
                    "status": "error",
                    "message": f"Section '## {section_header}' not found.",
                    "available_sections": available,
                }, indent=2, ensure_ascii=False)

            target_path.write_text(updated, encoding="utf-8")
            record_tool_call("update_tech_stack", stack=stack)
            return json.dumps({
                "status": "success",
                "mode": "replace_section",
                "stack": stack,
                "file": str(target_path.relative_to(PROJECT_ROOT)),
                "replaced_section": section_header,
                "message": f"Section '## {section_header}' updated successfully.",
            }, indent=2, ensure_ascii=False)

        return json.dumps({"status": "error", "message": "Unexpected state."}, indent=2)

    @mcp.tool()
    async def usage_stats(date: str = "") -> str:
        """Get daily usage analytics: tech stack usage frequency and satisfaction score.

        Call this tool when user asks to:
        - View usage statistics or analytics
        - Check which tech stacks are most used
        - See satisfaction score or query patterns

        Satisfaction score (0–100): higher = diverse queries (good),
        lower = repeated/similar queries (knowledge base may need improvement).

        Args:
            date: Date string YYYY-MM-DD (default: today).

        Returns:
            JSON with tool usage, stack usage, and satisfaction metrics.
        """
        return get_daily_stats(date if date else None)
