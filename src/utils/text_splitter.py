"""Text splitter — Code-Aware (Brace + Indentation) + Text Fallback.

Provides ``recursive_text_split`` as the main entry point:

- **Brace-based languages** (Kotlin, Dart, Swift, Java, TypeScript, C):
  Splits at top-level boundaries without breaking ``{ }`` blocks.
- **Indentation-based languages** (Python, YAML):
  Splits at top-level ``def``/``class`` boundaries using indent depth.
  Never cuts inside a function or class body.
- **Text** (prose, markdown, logs):
  Falls back to separator-based splitting.

This module is pure Python with **zero external dependencies**.

Phase 8 rewrite: dual-strategy code detection + indent-aware splitting.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEPARATORS: list[str] = ["\n\n", "\n", ". ", " "]
DEFAULT_CHUNK_SIZE: int = 2500
DEFAULT_CHUNK_OVERLAP: int = 150
CODE_CHUNK_SIZE: int = 2500

# Keywords for brace-based languages (split-point detection at depth 0).
BRACE_KEYWORDS: set[str] = {
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
    # TypeScript / JavaScript
    "function",
    "export",
    "const",
    "let",
}

# Keywords for Python indentation detection.
_PYTHON_BLOCK_STARTERS: tuple[str, ...] = (
    "def ",
    "async def ",
    "class ",
)
_PYTHON_IMPORT_PREFIXES: tuple[str, ...] = (
    "import ",
    "from ",
)


# ---------------------------------------------------------------------------
# Indentation helpers
# ---------------------------------------------------------------------------


def _indent_level(line: str) -> int:
    """Return the indentation level of *line* (number of leading spaces).

    Tabs are expanded to 4 spaces (PEP 8 standard).
    """
    expanded: str = line.replace("\t", "    ")
    return len(expanded) - len(expanded.lstrip())


def _is_python_top_level(stripped: str) -> bool:
    """Check if a stripped line starts a Python top-level block.

    Matches: ``def``, ``async def``, ``class``, ``@decorator``, or
    top-level assignments/constants.
    """
    return stripped.startswith(_PYTHON_BLOCK_STARTERS) or stripped.startswith("@")


# ---------------------------------------------------------------------------
# Code Detection
# ---------------------------------------------------------------------------


def is_code_content(text: str) -> bool:
    """Heuristic: detect if *text* is source code (not prose).

    Two independent strategies — either one returning True is sufficient:

    1. **Brace-based** (Kotlin, Java, Dart, Swift, TypeScript, C):
       ≥3 brace pairs ``{ }`` AND at least one top-level keyword present.
    2. **Indentation-based** (Python, YAML):
       Accumulates a signal score from Python-specific patterns:
       ``def``/``class`` with colon, ``@decorator``, indented body,
       ``import`` statements, docstrings ``\"\"\"``, type hints ``->``.
       Requires both ``def``/``class`` AND score ≥ 4.

    Args:
        text: The text content to classify.

    Returns:
        True if the text looks like source code, False otherwise.
    """
    lines: list[str] = text.split("\n")[:150]

    # ── Strategy 1: Brace-based (C-family languages) ──────────
    brace_count: int = min(text.count("{"), text.count("}"))
    if brace_count >= 3:
        for line in lines:
            stripped: str = line.lstrip()
            if not stripped:
                continue
            first_word: str = (
                stripped.split("(")[0].split("{")[0].split(":")[0].split(" ")[0]
            )
            if first_word in BRACE_KEYWORDS:
                return True
            # Skip annotations/comments, keep scanning
            if stripped.startswith("@") or stripped.startswith("//"):
                continue

    # ── Strategy 2: Indentation-based (Python / YAML) ─────────
    python_score: int = 0
    has_block_starter: bool = False
    indented_lines: int = 0
    total_non_empty: int = 0

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped:
            continue
        total_non_empty += 1

        # Count indented lines (4+ spaces or tab)
        if _indent_level(line) >= 4:
            indented_lines += 1

        # Decorator: @something (not @@)
        if stripped.startswith("@") and not stripped.startswith("@@"):
            python_score += 1

        # def / class / async def with trailing colon
        if stripped.startswith(_PYTHON_BLOCK_STARTERS):
            if stripped.rstrip().endswith(":"):
                has_block_starter = True
                python_score += 2
                # Bonus: next non-empty line is indented
                for j in range(i + 1, min(i + 5, len(lines))):
                    next_line: str = lines[j]
                    if next_line.strip():
                        if next_line[0] in (" ", "\t"):
                            python_score += 2
                        break

        # import / from ... import
        if stripped.startswith(_PYTHON_IMPORT_PREFIXES):
            python_score += 1

        # Docstrings
        if stripped.startswith('"""') or stripped.startswith("'''"):
            python_score += 1

        # Type hints in function signature
        if " -> " in stripped and "def " in stripped:
            python_score += 1

    # Python verdict: need def/class AND enough signals
    if has_block_starter and python_score >= 4:
        return True

    # Fallback: high ratio of indented lines suggests code
    if total_non_empty >= 10 and has_block_starter:
        indent_ratio: float = indented_lines / total_non_empty
        if indent_ratio >= 0.3:
            return True

    return False


# ---------------------------------------------------------------------------
# Detect language family
# ---------------------------------------------------------------------------


def _is_indent_based(text: str) -> bool:
    """Determine if code uses indentation (Python/YAML) vs braces.

    Simple heuristic: if brace pairs < 3 AND Python signals are present,
    it's indentation-based.  Otherwise assume brace-based.
    """
    brace_count: int = min(text.count("{"), text.count("}"))
    if brace_count >= 3:
        return False

    # Check for Python patterns in first 80 lines
    for line in text.split("\n")[:80]:
        stripped: str = line.lstrip()
        if stripped.startswith(_PYTHON_BLOCK_STARTERS):
            if stripped.rstrip().endswith(":"):
                return True

    return False


# ---------------------------------------------------------------------------
# Code-Aware Splitting: Brace-Based
# ---------------------------------------------------------------------------


def _brace_split(text: str, chunk_size: int) -> list[str]:
    """Split brace-based source code at top-level boundaries.

    Algorithm:
    1. Scan line-by-line, tracking ``brace_depth``.
    2. A **split point** is any blank line or keyword line where
       ``brace_depth == 0``.
    3. Group lines into top-level blocks, then merge into chunks.
    4. A single block exceeding ``chunk_size`` is kept intact.

    Args:
        text: Source code text.
        chunk_size: Target chunk size in characters.

    Returns:
        List of code chunks with intact brace balance.
    """
    lines: list[str] = text.split("\n")
    blocks: list[str] = []
    current_block: list[str] = []
    brace_depth: int = 0

    for line in lines:
        stripped: str = line.strip()

        # Track brace depth (skip lines that are pure string content)
        if not stripped.startswith('"') and not stripped.startswith("'"):
            brace_depth += line.count("{") - line.count("}")
            if brace_depth < 0:
                brace_depth = 0

        # Detect split point at top-level scope
        is_split: bool = False
        if brace_depth == 0 and current_block:
            if not stripped:
                is_split = True
            else:
                first_word: str = (
                    stripped.split("(")[0].split("{")[0].split(":")[0].split(" ")[0]
                )
                if first_word in BRACE_KEYWORDS or stripped.startswith("@"):
                    is_split = True

        if is_split:
            block_text: str = "\n".join(current_block).strip()
            if block_text:
                blocks.append(block_text)
            current_block = [line]
        else:
            current_block.append(line)

    # Emit last block
    if current_block:
        block_text = "\n".join(current_block).strip()
        if block_text:
            blocks.append(block_text)

    return _merge_blocks(blocks, chunk_size)


# ---------------------------------------------------------------------------
# Code-Aware Splitting: Indentation-Based (Python)
# ---------------------------------------------------------------------------


def _indent_split(text: str, chunk_size: int) -> list[str]:
    """Split indentation-based code (Python) at top-level boundaries.

    Algorithm:
    1. Scan line-by-line, tracking **indent depth**.
    2. A **split point** is where indent returns to 0 AND:
       - Line is blank, OR
       - Line starts a new ``def``/``class``/``@decorator``, OR
       - Line is a top-level statement (import, assignment, etc.)
    3. Never cut inside a ``def`` or ``class`` body (indent > 0).
    4. Group into top-level blocks, then merge into chunks.
    5. Giant blocks (single class > chunk_size) are kept intact.

    Args:
        text: Python source code.
        chunk_size: Target chunk size in characters.

    Returns:
        List of code chunks with intact function/class boundaries.
    """
    lines: list[str] = text.split("\n")
    blocks: list[str] = []
    current_block: list[str] = []
    in_block_body: bool = False

    for line in lines:
        stripped: str = line.strip()
        indent: int = _indent_level(line)

        # Detect split points at top-level (indent == 0)
        is_split: bool = False

        if indent == 0 and current_block:
            if not stripped:
                # Blank line at top level — potential split point
                # Only split if we were inside a block body
                if in_block_body:
                    is_split = True
                    in_block_body = False
            elif _is_python_top_level(stripped):
                # New def/class/decorator at top level
                is_split = True
                in_block_body = False

        # Track if we're inside a function/class body
        if indent == 0 and stripped.startswith(_PYTHON_BLOCK_STARTERS):
            if stripped.rstrip().endswith(":"):
                in_block_body = True

        if is_split:
            block_text: str = "\n".join(current_block).rstrip()
            if block_text.strip():
                blocks.append(block_text.strip())
            # Start new block — include blank line if it's just whitespace
            if stripped:
                current_block = [line]
            else:
                current_block = []
        else:
            current_block.append(line)

    # Emit last block
    if current_block:
        block_text = "\n".join(current_block).strip()
        if block_text:
            blocks.append(block_text)

    # Edge case: no split points found (e.g., single function, no blank lines)
    if not blocks:
        return [text.strip()] if text.strip() else []

    return _merge_blocks(blocks, chunk_size)


# ---------------------------------------------------------------------------
# Shared: Merge small blocks into chunks
# ---------------------------------------------------------------------------


def _merge_blocks(blocks: list[str], chunk_size: int) -> list[str]:
    """Merge a list of code blocks into chunks up to *chunk_size*.

    Small adjacent blocks are joined with ``\\n\\n``.
    A single block exceeding ``chunk_size`` is kept intact (never split).

    Args:
        blocks: Top-level code blocks.
        chunk_size: Maximum target size per chunk.

    Returns:
        List of merged chunks.
    """
    if not blocks:
        return []

    chunks: list[str] = []
    current_chunk: str = ""

    for block in blocks:
        if not current_chunk:
            current_chunk = block
        elif len(current_chunk) + len(block) + 2 <= chunk_size:
            current_chunk = f"{current_chunk}\n\n{block}"
        else:
            chunks.append(current_chunk.strip())
            current_chunk = block

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks if chunks else blocks


# ---------------------------------------------------------------------------
# Public: Code-Aware Split (dispatches to brace or indent strategy)
# ---------------------------------------------------------------------------


def code_aware_split(
    text: str,
    chunk_size: int = CODE_CHUNK_SIZE,
) -> list[str]:
    """Split source code at top-level boundaries, preserving syntax.

    Automatically detects the language family:
    - **Brace-based** (Kotlin, Java, Dart, Swift, TypeScript, C):
      Tracks ``{ }`` depth and splits at depth 0.
    - **Indentation-based** (Python, YAML):
      Tracks indent level and splits at level 0 between blocks.

    In both cases, a single top-level block exceeding ``chunk_size``
    (e.g., a giant class) is kept intact — broken code is worse than
    a large chunk.

    Args:
        text: Source code content.
        chunk_size: Target maximum chunk size in characters.

    Returns:
        List of code chunks with intact syntax boundaries.
    """
    if not text.strip():
        return []
    if len(text) <= chunk_size:
        return [text.strip()]

    if _is_indent_based(text):
        return _indent_split(text, chunk_size)

    return _brace_split(text, chunk_size)


# ---------------------------------------------------------------------------
# Text Splitting (separator-based fallback)
# ---------------------------------------------------------------------------


def text_split(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    separators: list[str] | None = None,
) -> list[str]:
    """Split plain text at semantic anchor points.

    Priority order: ``\\n\\n`` → ``\\n`` → ``. `` → `` ``
    Fallback for non-code content (prose, markdown, logs).

    Args:
        text: Plain text content.
        chunk_size: Maximum chunk size.
        chunk_overlap: Number of characters to overlap between chunks.
        separators: Custom separator list (default: SEPARATORS).

    Returns:
        List of text chunks.
    """
    if not text.strip():
        return []
    if len(text) <= chunk_size:
        return [text.strip()]

    seps: list[str] = separators if separators is not None else list(SEPARATORS)

    # Fallback: character-based splitting
    if not seps:
        chunks: list[str] = []
        start: int = 0
        while start < len(text):
            end: int = min(start + chunk_size, len(text))
            chunk: str = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start += chunk_size - chunk_overlap
        return chunks

    sep: str = seps[0]
    remaining_seps: list[str] = seps[1:]
    segments: list[str] = text.split(sep)

    merged_chunks: list[str] = []
    current_chunk: str = ""

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        candidate: str = f"{current_chunk}{sep}{segment}" if current_chunk else segment
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

    # Apply overlap between chunks
    if chunk_overlap > 0 and len(merged_chunks) > 1:
        overlapped: list[str] = [merged_chunks[0]]
        for i in range(1, len(merged_chunks)):
            prev: str = merged_chunks[i - 1]
            tail: str = prev[-chunk_overlap:] if len(prev) > chunk_overlap else prev
            for break_sep in SEPARATORS:
                idx: int = tail.find(break_sep)
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

    - **Code** (Kotlin, Java, Python, TypeScript, etc.):
      Uses ``code_aware_split`` which dispatches to brace-based or
      indentation-based splitting depending on the language family.
    - **Text** (prose, markdown, logs):
      Uses separator-based splitting.

    Args:
        text: Content to split.
        chunk_size: Target maximum chunk size.
        chunk_overlap: Overlap between text chunks (code chunks don't overlap).
        separators: Custom separators for text splitting.

    Returns:
        List of chunks preserving semantic/syntactic integrity.
    """
    if not text.strip():
        return []

    if is_code_content(text):
        return code_aware_split(text, chunk_size=chunk_size)

    return text_split(text, chunk_size, chunk_overlap, separators)
