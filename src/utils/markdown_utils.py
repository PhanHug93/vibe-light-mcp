"""Markdown Utilities — Section parsing and merging for knowledge files.

Standalone module, no MCP dependency. Extracted from ``server.py`` (SRP).

Usage::

    from src.utils.markdown_utils import (
        parse_md_sections, merge_md_sections, replace_md_section,
    )
"""

from __future__ import annotations

import re


def parse_md_sections(content: str) -> dict[str, str]:
    """Parse markdown into ``{header: body}`` by ``## `` (H2) headers.

    The key ``"__preamble__"`` holds any content before the first H2.
    Keys are the header text (without ``## `` prefix), values are the
    body text following that header up to the next H2 or end-of-file.
    """
    sections: dict[str, str] = {}
    parts = re.split(r"(?m)^## ", content)

    if parts:
        preamble = parts[0].strip()
        if preamble:
            sections["__preamble__"] = preamble

    for part in parts[1:]:
        lines = part.split("\n", 1)
        header = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        sections[header] = body

    return sections


def merge_md_sections(
    existing: str,
    new_content: str,
) -> tuple[str, list[str], list[str]]:
    """Merge new H2 sections into existing markdown, skipping duplicates.

    Returns:
        (merged_text, added_headers, skipped_headers)
    """
    existing_sections = parse_md_sections(existing)
    new_sections = parse_md_sections(new_content)

    added: list[str] = []
    skipped: list[str] = []

    for header, body in new_sections.items():
        if header == "__preamble__":
            continue
        if header in existing_sections:
            skipped.append(header)
        else:
            added.append(header)
            existing += f"\n\n## {header}\n\n{body}"

    return existing.strip() + "\n", added, skipped


def replace_md_section(
    content: str,
    section_header: str,
    new_body: str,
) -> tuple[str, bool]:
    """Replace the body of a specific ``## section_header`` in *content*.

    Returns:
        (updated_content, was_found)
    """
    pattern = (
        r"(^## " + re.escape(section_header) + r"[ \t]*\n)"  # header line
        r"(.*?)"  # body (lazy)
        r"(?=^## |\Z)"  # next H2 or EOF
    )
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if not match:
        return content, False

    replacement = match.group(1) + "\n" + new_body.strip() + "\n\n"
    updated = content[: match.start()] + replacement + content[match.end() :]
    return updated, True
