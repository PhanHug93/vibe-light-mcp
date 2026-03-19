"""Tests for text_splitter module — code-aware + text fallback chunking.

Phase 8: Added Python indentation-based splitting tests.
"""

from __future__ import annotations

from src.utils.text_splitter import (
    code_aware_split,
    is_code_content,
    recursive_text_split,
    text_split,
    _is_indent_based,
    _indent_level,
)


# ---------------------------------------------------------------------------
# Code Detection — Brace-based
# ---------------------------------------------------------------------------


def test_detects_kotlin_code() -> None:
    kotlin = """class Foo {
    fun bar() { val x = 1 }
}
class Baz { fun q() { } }
object X { }"""
    assert is_code_content(kotlin) is True


def test_rejects_prose() -> None:
    prose = "This is just regular text. No code here at all. " * 10
    assert is_code_content(prose) is False


def test_rejects_few_braces() -> None:
    text = "Some {json} data with {braces}"
    assert is_code_content(text) is False


# ---------------------------------------------------------------------------
# Code Detection — Python (indentation-based)
# ---------------------------------------------------------------------------


def test_detects_python_code() -> None:
    python = '''import logging
from pathlib import Path


def hello(name: str) -> str:
    """Say hello."""
    return f"Hello, {name}!"


class Greeter:
    """A greeter class."""

    def __init__(self, name: str) -> None:
        self.name = name

    def greet(self) -> str:
        return hello(self.name)
'''
    assert is_code_content(python) is True


def test_detects_python_with_decorators() -> None:
    python = """from functools import wraps


@wraps
def decorator(func):
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


@decorator
def my_function():
    pass
"""
    assert is_code_content(python) is True


def test_detects_python_async() -> None:
    python = '''import asyncio


async def fetch_data(url: str) -> dict:
    """Fetch data from URL."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()
'''
    assert is_code_content(python) is True


def test_rejects_markdown() -> None:
    markdown = """# Title

Some paragraph text here.

## Section 2

More text and content.

- Item 1
- Item 2
"""
    assert is_code_content(markdown) is False


# ---------------------------------------------------------------------------
# Language Family Detection
# ---------------------------------------------------------------------------


def test_indent_based_python() -> None:
    python = """def hello():
    print("hi")
"""
    assert _is_indent_based(python) is True


def test_indent_based_kotlin() -> None:
    kotlin = """class Foo {
    fun bar() { }
}"""
    assert _is_indent_based(kotlin) is False


# ---------------------------------------------------------------------------
# Indent Level Helper
# ---------------------------------------------------------------------------


def test_indent_level_spaces() -> None:
    assert _indent_level("    code") == 4
    assert _indent_level("        code") == 8
    assert _indent_level("code") == 0


def test_indent_level_tabs() -> None:
    assert _indent_level("\tcode") == 4
    assert _indent_level("\t\tcode") == 8


# ---------------------------------------------------------------------------
# Code-Aware Splitting — Brace-based
# ---------------------------------------------------------------------------


def test_code_split_preserves_balanced_braces() -> None:
    kotlin = """sealed interface UiState {
    object Loading : UiState
    data class Success(val data: List<String>) : UiState
}

class ViewModel {
    fun loadData() {
        viewModelScope.launch {
            try { val r = fetch() } catch (e: Exception) { }
        }
    }
}"""
    chunks = code_aware_split(kotlin, chunk_size=200)
    for chunk in chunks:
        assert chunk.count("{") == chunk.count("}"), (
            f"Unbalanced braces in: {chunk[:80]}..."
        )


def test_code_split_keeps_giant_class_intact() -> None:
    # A single class that exceeds chunk_size — should NOT be split
    big_class = "class Big {\n" + "    val x = 1\n" * 100 + "}"
    chunks = code_aware_split(big_class, chunk_size=200)
    # Entire class should be in one chunk
    assert len(chunks) == 1
    assert chunks[0].count("{") == chunks[0].count("}")


def test_small_code_returned_as_single_chunk() -> None:
    small = 'fun hello() { println("hi") }'
    chunks = code_aware_split(small, chunk_size=2500)
    assert len(chunks) == 1


# ---------------------------------------------------------------------------
# Code-Aware Splitting — Python (indentation-based)
# ---------------------------------------------------------------------------


def test_python_split_never_cuts_inside_function() -> None:
    """Each function should remain intact in its chunk."""
    python = """def function_one():
    x = 1
    y = 2
    return x + y


def function_two():
    a = "hello"
    b = "world"
    return f"{a} {b}"


def function_three():
    for i in range(10):
        print(i)
"""
    chunks = code_aware_split(python, chunk_size=100)
    # Every chunk should contain complete def blocks
    for chunk in chunks:
        # If chunk starts with 'def', it should contain the full body
        if chunk.strip().startswith("def "):
            lines = chunk.split("\n")
            # First line is def, subsequent should be indented
            for line in lines[1:]:
                if line.strip():  # non-empty lines after def
                    assert line[0] in (" ", "\t"), f"Body line not indented: '{line}'"


def test_python_split_keeps_class_intact() -> None:
    """A class with methods should NOT be split across chunks."""
    big_class = '''class MyService:
    """A service class."""

    def __init__(self):
        self.data = []

    def process(self):
        for item in self.data:
            result = self._transform(item)
            self._store(result)

    def _transform(self, item):
        return item * 2

    def _store(self, result):
        self.data.append(result)
'''
    chunks = code_aware_split(big_class, chunk_size=2500)
    # Class should be in one chunk since it's under chunk_size
    assert len(chunks) == 1
    assert "class MyService:" in chunks[0]
    assert "def _store" in chunks[0]


def test_python_split_separates_top_level_functions() -> None:
    """Multiple top-level functions should be separable."""
    funcs = []
    for i in range(5):
        funcs.append(f"""def func_{i}(x: int) -> int:
    \"\"\"Function {i}.\"\"\"
    result = x * {i}
    return result
""")
    python = "\n\n".join(funcs)

    chunks = code_aware_split(python, chunk_size=200)
    assert len(chunks) >= 2, "Should split into multiple chunks"

    # Each chunk should have complete def blocks
    for chunk in chunks:
        # Count def statements
        defs = [line for line in chunk.split("\n") if line.strip().startswith("def ")]
        assert len(defs) >= 1, "Each chunk should have at least one def"


def test_python_split_small_file_single_chunk() -> None:
    """Small Python file should be a single chunk."""
    python = """def hello():
    print("Hello!")
"""
    chunks = code_aware_split(python, chunk_size=2500)
    assert len(chunks) == 1


def test_python_split_with_decorators() -> None:
    """Decorators should stay attached to their function."""
    python = """import functools


@functools.lru_cache
def expensive_call(n: int) -> int:
    return sum(range(n))


@functools.wraps
def another_func():
    pass
"""
    chunks = code_aware_split(python, chunk_size=150)
    # Decorator should be in same chunk as its function
    for chunk in chunks:
        if "@functools.lru_cache" in chunk:
            assert "def expensive_call" in chunk


# ---------------------------------------------------------------------------
# Text Splitting
# ---------------------------------------------------------------------------


def test_text_split_respects_chunk_size() -> None:
    prose = "Word " * 500  # ~2500 chars
    chunks = text_split(prose, chunk_size=300)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) < 1500  # generous slack for overlap


def test_text_split_empty() -> None:
    assert text_split("") == []
    assert text_split("   ") == []


# ---------------------------------------------------------------------------
# recursive_text_split (gateway)
# ---------------------------------------------------------------------------


def test_gateway_routes_code_to_code_aware() -> None:
    kotlin = """class A {
    fun a() { }
}
class B {
    fun b() { }
}
class C {
    fun c() { }
}"""
    chunks = recursive_text_split(kotlin, chunk_size=50)
    for chunk in chunks:
        assert chunk.count("{") == chunk.count("}")


def test_gateway_routes_python_to_indent_aware() -> None:
    python = '''import os
from pathlib import Path


def read_file(path: str) -> str:
    """Read file content."""
    with open(path) as f:
        return f.read()


def write_file(path: str, content: str) -> None:
    """Write content to file."""
    Path(path).write_text(content)
'''
    chunks = recursive_text_split(python, chunk_size=200)
    assert len(chunks) >= 1
    # Each chunk should contain complete Python constructs
    for chunk in chunks:
        if "def " in chunk:
            assert ":" in chunk  # function signature intact


def test_gateway_routes_text_to_text_split() -> None:
    prose = "Hello world. " * 200
    chunks = recursive_text_split(prose, chunk_size=300)
    assert len(chunks) > 1


def test_gateway_empty() -> None:
    assert recursive_text_split("") == []
    assert recursive_text_split("   ") == []
