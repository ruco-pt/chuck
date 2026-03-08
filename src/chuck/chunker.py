"""Token-aware content chunking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple


@dataclass
class FileContent:
    """A file with its content and token count."""
    path: str
    content: str
    tokens: int
    is_changed: bool = False


@dataclass
class Chunk:
    """A single chunk of content fitting within a token budget."""
    index: int          # 1-based
    total: int          # total chunks (filled in after all chunks created)
    files: List[FileContent] = field(default_factory=list)
    excluded_files: List[str] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return sum(f.tokens for f in self.files)


def _split_file_by_functions(content: str, budget: int, counter: Callable[[str], int]) -> List[str]:
    """Split a file at function/class boundaries."""
    # Match Python/JS/TS function or class definitions
    boundary_re = re.compile(r"^(?:def |class |function |async def |export (?:default )?(?:class|function))", re.MULTILINE)
    positions = [m.start() for m in boundary_re.finditer(content)]

    if not positions:
        # Fall back to line-based splitting
        return _split_by_lines(content, budget, counter)

    parts = []
    current_start = 0
    for pos in positions[1:]:
        chunk = content[current_start:pos]
        parts.append((current_start, pos, chunk))
        current_start = pos
    parts.append((current_start, len(content), content[current_start:]))

    # Group parts until budget is exceeded
    segments = []
    current = ""
    for _, _, text in parts:
        candidate = current + text
        if counter(candidate) <= budget:
            current = candidate
        else:
            if current:
                segments.append(current)
            current = text
    if current:
        segments.append(current)

    return segments


def _split_by_headings(content: str, budget: int, counter: Callable[[str], int]) -> List[str]:
    """Split markdown content at heading boundaries."""
    heading_re = re.compile(r"^#{1,3} .+$", re.MULTILINE)
    positions = [m.start() for m in heading_re.finditer(content)]

    if not positions:
        return _split_by_lines(content, budget, counter)

    segments = []
    current = content[:positions[0]] if positions[0] > 0 else ""
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(content)
        section = content[pos:end]
        candidate = current + section
        if counter(candidate) <= budget:
            current = candidate
        else:
            if current:
                segments.append(current)
            current = section
    if current:
        segments.append(current)

    return [s for s in segments if s.strip()]


def _split_by_lines(content: str, budget: int, counter: Callable[[str], int]) -> List[str]:
    """Split content into segments by line count, fitting within budget."""
    lines = content.splitlines(keepends=True)
    segments = []
    current_lines: List[str] = []

    for line in lines:
        current_lines.append(line)
        if counter("".join(current_lines)) > budget:
            if len(current_lines) > 1:
                segments.append("".join(current_lines[:-1]))
                current_lines = [line]
            else:
                # Single line exceeds budget — force include it
                segments.append(line)
                current_lines = []

    if current_lines:
        segments.append("".join(current_lines))

    return segments


def _is_markdown(path: str) -> bool:
    return path.endswith((".md", ".rst", ".txt"))


def _split_large_file(
    fc: FileContent,
    budget: int,
    counter: Callable[[str], int],
) -> List[FileContent]:
    """Split a file that exceeds the budget into sub-chunks."""
    content = fc.content
    ext = Path(fc.path).suffix.lower()

    if ext in {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".cpp", ".c", ".cs", ".rb", ".rs"}:
        segments = _split_file_by_functions(content, budget, counter)
    elif _is_markdown(fc.path):
        segments = _split_by_headings(content, budget, counter)
    else:
        segments = _split_by_lines(content, budget, counter)

    results = []
    for i, seg in enumerate(segments):
        seg_path = f"{fc.path}[part {i+1}/{len(segments)}]"
        results.append(FileContent(
            path=seg_path,
            content=seg,
            tokens=counter(seg),
            is_changed=fc.is_changed,
        ))
    return results


def chunk_files(
    files: List[FileContent],
    budget: int,
    counter: Callable[[str], int],
    prioritize_changed: bool = True,
) -> List[Chunk]:
    """
    Distribute files into chunks, each fitting within the token budget.

    Strategy:
    1. Sort changed files first (if prioritize_changed).
    2. Group files by directory for locality.
    3. If a file exceeds the budget alone, split it.
    4. Accumulate files into chunks until budget is hit.
    """
    if not files or budget <= 0:
        if not files:
            return []
        # No budget — single chunk with all files
        chunk = Chunk(index=1, total=1, files=files)
        return [chunk]

    # Sort: changed files first, then by directory grouping
    def sort_key(fc: FileContent) -> Tuple:
        priority = 0 if (prioritize_changed and fc.is_changed) else 1
        parts = Path(fc.path).parts
        return (priority, parts[:-1], parts[-1])

    sorted_files = sorted(files, key=sort_key)

    chunks: List[Chunk] = []
    current_chunk = Chunk(index=1, total=0)
    current_tokens = 0

    for fc in sorted_files:
        if fc.tokens > budget:
            # File is too large — split it
            sub_files = _split_large_file(fc, budget, counter)
        else:
            sub_files = [fc]

        for sub in sub_files:
            if current_tokens + sub.tokens > budget and current_chunk.files:
                chunks.append(current_chunk)
                current_chunk = Chunk(index=len(chunks) + 1, total=0)
                current_tokens = 0
            current_chunk.files.append(sub)
            current_tokens += sub.tokens

    if current_chunk.files:
        chunks.append(current_chunk)

    # Set total on all chunks
    total = len(chunks)
    for chunk in chunks:
        chunk.total = total

    return chunks
