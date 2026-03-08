"""Tests for token-aware chunking."""

import pytest
from chuck.chunker import FileContent, Chunk, chunk_files


def make_fc(path: str, tokens: int, is_changed: bool = False) -> FileContent:
    return FileContent(path=path, content="x" * tokens, tokens=tokens, is_changed=is_changed)


def word_counter(text: str) -> int:
    return len(text)  # 1 char = 1 "token" for test simplicity


def test_single_chunk_fits():
    files = [make_fc("a.py", 100), make_fc("b.py", 200)]
    chunks = chunk_files(files, budget=500, counter=word_counter)
    assert len(chunks) == 1
    assert chunks[0].total == 1
    assert len(chunks[0].files) == 2


def test_splits_into_multiple_chunks():
    files = [make_fc("a.py", 300), make_fc("b.py", 300), make_fc("c.py", 300)]
    chunks = chunk_files(files, budget=400, counter=word_counter)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.tokens <= 400


def test_changed_files_first():
    files = [
        make_fc("unchanged.py", 100, is_changed=False),
        make_fc("changed.py", 100, is_changed=True),
    ]
    chunks = chunk_files(files, budget=150, counter=word_counter)
    # First chunk should contain the changed file
    first_paths = {f.path for f in chunks[0].files}
    assert "changed.py" in first_paths


def test_chunk_indices():
    files = [make_fc(f"f{i}.py", 200) for i in range(5)]
    chunks = chunk_files(files, budget=250, counter=word_counter)
    for i, chunk in enumerate(chunks):
        assert chunk.index == i + 1
        assert chunk.total == len(chunks)


def test_no_budget_single_chunk():
    files = [make_fc("a.py", 1000), make_fc("b.py", 1000)]
    chunks = chunk_files(files, budget=0, counter=word_counter)
    # budget=0 means no limit — single chunk
    assert len(chunks) == 1


def test_empty_files():
    chunks = chunk_files([], budget=1000, counter=word_counter)
    assert chunks == []


def test_large_file_split():
    """A file exceeding the budget alone gets split."""
    big_content = "abcde\n" * 1000  # 6000 chars
    big_file = FileContent(path="huge.py", content=big_content, tokens=6000)
    chunks = chunk_files([big_file], budget=1000, counter=lambda t: len(t))
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.tokens <= 1000


def test_chunk_tokens_property():
    files = [make_fc("a.py", 100), make_fc("b.py", 200)]
    chunks = chunk_files(files, budget=1000, counter=word_counter)
    assert chunks[0].tokens == 300
