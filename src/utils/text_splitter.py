"""Text splitter — Code-Aware + Text Fallback.

Provides ``recursive_text_split`` as the main entry point:
- Detects source code (Kotlin, Dart, Swift, Java, Python, TypeScript)
  and splits at top-level boundaries without breaking ``{ }`` blocks.
- Falls back to separator-based splitting for prose / markdown / logs.

This module is pure Python with **zero external dependencies**.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEPARATORS: list[str] = ["\n\n", "\n", ". ", " "]
DEFAULT_CHUNK_SIZE: int = 2500  # increased from 1000 to contain full classes
DEFAULT_CHUNK_OVERLAP: int = 150
CODE_CHUNK_SIZE: int = 2500  # code-aware chunking target size

# Keywords that typically start a top-level code block (Kotlin, Dart, Swift,
# Java, Python, TypeScript).  Used for split-point detection at brace depth 0.
TOP_LEVEL_KEYWORDS: set[str] = {
    # Kotlin / Java
    "class",
    "object",
    "interface",
    "enum",
    "fun",
    "val",
    "var",
    "abstract",
    "open",
    "data",
    "sealed",
    "annotation",
    "suspend",
    "override",
    "private",
    "protected",
    "internal",
    "public",
    # Dart / Flutter
    "void",
    "Future",
    "Stream",
    "Widget",
    "State",
    # Swift
    "func",
    "struct",
    "protocol",
    "extension",
    # Python
    "def",
    "async",
    # TypeScript / JavaScript
    "function",
    "export",
    "const",
    "let",
}


# ---------------------------------------------------------------------------
# Code Detection
# ---------------------------------------------------------------------------


def is_code_content(text: str) -> bool:
    """Heuristic: detect if *text* is source code (not prose).

    Checks for:
    - ≥3 brace pairs ``{ }``
    - At least one top-level keyword present
    """
    brace_count = min(text.count("{"), text.count("}"))
    if brace_count < 3:
        return False
    for line in text.split("\n")[:100]:  # scan first 100 lines only
        stripped = line.lstrip()
        if not stripped:
            continue
        first_word = stripped.split("(")[0].split("{")[0].split(":")[0].split(" ")[0]
        if first_word in TOP_LEVEL_KEYWORDS:
            return True
        # Annotations / decorators: skip and continue scanning
        if (
            stripped.startswith("@")
            or stripped.startswith("//")
            or stripped.startswith("#")
        ):
            continue
    return False


# ---------------------------------------------------------------------------
# Code-Aware Splitting
# ---------------------------------------------------------------------------


def code_aware_split(
    text: str,
    chunk_size: int = CODE_CHUNK_SIZE,
) -> list[str]:
    """Split source code at top-level boundaries, respecting brace depth.

    Algorithm:
    1. Scan line-by-line, tracking ``brace_depth`` (``{`` increments, ``}``
       decrements).
    2. A **split point** is any blank line or top-level keyword line where
       ``brace_depth == 0``.
    3. Accumulate lines into the current chunk.  When adding the next
       block would exceed ``chunk_size``, emit the current chunk and start
       a new one.
    4. If a single top-level block exceeds ``chunk_size`` (giant class),
       keep it intact — broken code is worse than a large chunk.

    Returns a list of code chunks with intact syntax.
    """
    if not text.strip():
        return []
    if len(text) <= chunk_size:
        return [text.strip()]

    lines = text.split("\n")
    blocks: list[str] = []  # list of top-level blocks
    current_block_lines: list[str] = []
    brace_depth: int = 0

    for line in lines:
        # Track brace depth (simple counter — handles Kotlin/Dart/Swift/Java)
        # Skip braces inside string literals (rough heuristic: ignore lines
        # that are purely string content — good enough for 95% of cases)
        stripped = line.strip()
        if not stripped.startswith('"') and not stripped.startswith("'"):
            brace_depth += line.count("{") - line.count("}")
            # Clamp to 0 (handles edge cases like template strings)
            if brace_depth < 0:
                brace_depth = 0

        # Detect split point: brace_depth == 0 AND (blank line or top-level keyword)
        is_split_point = False
        if brace_depth == 0 and current_block_lines:
            if not stripped:
                # Blank line at top level
                is_split_point = True
            else:
                first_word = (
                    stripped.split("(")[0].split("{")[0].split(":")[0].split(" ")[0]
                )
                if first_word in TOP_LEVEL_KEYWORDS or stripped.startswith("@"):
                    is_split_point = True

        if is_split_point:
            # Emit current block
            block_text = "\n".join(current_block_lines).strip()
            if block_text:
                blocks.append(block_text)
            current_block_lines = [line]
        else:
            current_block_lines.append(line)

    # Don't forget the last block
    if current_block_lines:
        block_text = "\n".join(current_block_lines).strip()
        if block_text:
            blocks.append(block_text)

    if not blocks:
        return [text.strip()]

    # --- Merge small blocks into chunks up to chunk_size ---
    chunks: list[str] = []
    current_chunk = ""

    for block in blocks:
        if not current_chunk:
            current_chunk = block
        elif len(current_chunk) + len(block) + 2 <= chunk_size:  # +2 for "\n\n"
            current_chunk = f"{current_chunk}\n\n{block}"
        else:
            # Emit current chunk
            chunks.append(current_chunk.strip())
            current_chunk = block

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks if chunks else [text.strip()]


# ---------------------------------------------------------------------------
# Text Splitting (separator-based)
# ---------------------------------------------------------------------------


def text_split(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    separators: list[str] | None = None,
) -> list[str]:
    """Split plain text at semantic anchor points.

    Priority order: ``\\n\\n`` → ``\\n`` → ``. `` → `` ``
    Fallback for non-code content.
    """
    if not text.strip():
        return []
    if len(text) <= chunk_size:
        return [text.strip()]

    seps = separators if separators is not None else list(SEPARATORS)

    if not seps:
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start += chunk_size - chunk_overlap
        return chunks

    sep = seps[0]
    remaining_seps = seps[1:]
    segments = text.split(sep)

    merged_chunks: list[str] = []
    current_chunk = ""

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        candidate = f"{current_chunk}{sep}{segment}" if current_chunk else segment
        if len(candidate) <= chunk_size:
            current_chunk = candidate
        else:
            if current_chunk:
                merged_chunks.append(current_chunk.strip())
            if len(segment) > chunk_size:
                merged_chunks.extend(
                    text_split(segment, chunk_size, chunk_overlap, remaining_seps)
                )
                current_chunk = ""
            else:
                current_chunk = segment

    if current_chunk.strip():
        merged_chunks.append(current_chunk.strip())

    if chunk_overlap > 0 and len(merged_chunks) > 1:
        overlapped: list[str] = [merged_chunks[0]]
        for i in range(1, len(merged_chunks)):
            prev = merged_chunks[i - 1]
            tail = prev[-chunk_overlap:] if len(prev) > chunk_overlap else prev
            for break_sep in SEPARATORS:
                idx = tail.find(break_sep)
                if idx != -1:
                    tail = tail[idx + len(break_sep) :]
                    break
            overlapped.append(f"{tail.strip()} {merged_chunks[i]}".strip())
        return overlapped

    return merged_chunks


# ---------------------------------------------------------------------------
# Public API — Smart Splitter
# ---------------------------------------------------------------------------


def recursive_text_split(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    separators: list[str] | None = None,
) -> list[str]:
    """Smart split: auto-detects code vs text and delegates accordingly.

    - **Code** (Kotlin, Dart, Swift, Java, Python, TypeScript):
      Uses ``code_aware_split`` with brace-depth tracking.
      Never cuts inside ``{ }`` blocks.
    - **Text** (prose, markdown, logs):
      Uses separator-based splitting (original algorithm).
    """
    if not text.strip():
        return []

    if is_code_content(text):
        return code_aware_split(text, chunk_size=chunk_size)

    return text_split(text, chunk_size, chunk_overlap, separators)
