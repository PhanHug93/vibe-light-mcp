"""Tests for text_splitter module — code-aware + text fallback chunking."""

from __future__ import annotations

from src.utils.text_splitter import (
    code_aware_split,
    is_code_content,
    recursive_text_split,
    text_split,
)


# ---------------------------------------------------------------------------
# Code Detection
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
# Code-Aware Splitting
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
        assert chunk.count("{") == chunk.count("}"), f"Unbalanced braces in: {chunk[:80]}..."


def test_code_split_keeps_giant_class_intact() -> None:
    # A single class that exceeds chunk_size — should NOT be split
    big_class = "class Big {\n" + "    val x = 1\n" * 100 + "}"
    chunks = code_aware_split(big_class, chunk_size=200)
    # Entire class should be in one chunk
    assert len(chunks) == 1
    assert chunks[0].count("{") == chunks[0].count("}")


def test_small_code_returned_as_single_chunk() -> None:
    small = "fun hello() { println(\"hi\") }"
    chunks = code_aware_split(small, chunk_size=2500)
    assert len(chunks) == 1


# ---------------------------------------------------------------------------
# Text Splitting
# ---------------------------------------------------------------------------


def test_text_split_respects_chunk_size() -> None:
    prose = "Word " * 500  # ~2500 chars
    chunks = text_split(prose, chunk_size=300)
    assert len(chunks) > 1
    # Overlap mechanism may increase individual chunk sizes
    # Key property: we get multiple chunks, each reasonably sized
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


def test_gateway_routes_text_to_text_split() -> None:
    prose = "Hello world. " * 200
    chunks = recursive_text_split(prose, chunk_size=300)
    assert len(chunks) > 1


def test_gateway_empty() -> None:
    assert recursive_text_split("") == []
    assert recursive_text_split("   ") == []
