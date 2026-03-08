"""Digest generation and formatting (markdown, xml, json)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

from .chunker import Chunk, FileContent, chunk_files
from .snapshot import FileDiff, Snapshot, SnapshotDiff
from .tokens import count_tokens


def _read_safe(abs_path: str) -> str:
    try:
        return Path(abs_path).read_text(encoding="utf-8", errors="replace")
    except (OSError, IOError):
        return ""


def _get_lang(path: str) -> str:
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".jsx": "jsx", ".tsx": "tsx", ".go": "go", ".rs": "rust",
        ".java": "java", ".c": "c", ".cpp": "cpp", ".cs": "csharp",
        ".rb": "ruby", ".sh": "bash", ".bash": "bash", ".zsh": "bash",
        ".json": "json", ".yaml": "yaml", ".yml": "yaml",
        ".toml": "toml", ".md": "markdown", ".html": "html",
        ".css": "css", ".sql": "sql", ".xml": "xml", ".txt": "",
    }
    return ext_map.get(Path(path).suffix.lower(), "")


# ─── Markdown format ──────────────────────────────────────────────────────────

def _chunk_header_md(chunk: Chunk, context_name: str) -> str:
    file_list = ", ".join(Path(f.path).name for f in chunk.files[:5])
    if len(chunk.files) > 5:
        file_list += f", +{len(chunk.files) - 5} more"
    lines = [
        f"<!-- Chunk {chunk.index}/{chunk.total} | Files: {len(chunk.files)} | Tokens: {chunk.tokens} -->",
        f"<!-- Files: {file_list} -->",
    ]
    if chunk.excluded_files:
        lines.append(f"<!-- Excluded: {', '.join(chunk.excluded_files)} -->")
    return "\n".join(lines) + "\n\n"


def _file_block_md(fc: FileContent) -> str:
    lang = _get_lang(fc.path)
    return (
        f"### {fc.path} ({fc.tokens} tokens)\n"
        f"```{lang}\n"
        f"{fc.content}\n"
        f"```\n\n"
    )


def _render_chunk_md(chunk: Chunk, context_name: str, include_header: bool) -> str:
    parts = []
    if include_header:
        parts.append(_chunk_header_md(chunk, context_name))
    for fc in chunk.files:
        parts.append(_file_block_md(fc))
    return "".join(parts)


def format_digest_markdown(
    context_name: str,
    snapshot: Snapshot,
    files_content: List[FileContent],
    chunks: List[Chunk],
) -> Union[str, List[str]]:
    ts = snapshot.timestamp
    total_tokens = sum(f.tokens for f in files_content)
    header = (
        f"# Context: {context_name}\n"
        f"## Snapshot: {ts} | Files: {len(files_content)} | Tokens: {total_tokens:,}\n\n"
    )
    multi_chunk = len(chunks) > 1

    if not multi_chunk:
        body = _render_chunk_md(chunks[0], context_name, include_header=False) if chunks else ""
        return header + body

    # Multiple chunks — return list of strings
    results = []
    for chunk in chunks:
        chunk_header = (
            f"# Context: {context_name} [Chunk {chunk.index}/{chunk.total}]\n"
            f"## Snapshot: {ts} | Files: {len(files_content)} total | "
            f"Chunk files: {len(chunk.files)} | Chunk tokens: {chunk.tokens:,}\n\n"
        )
        results.append(chunk_header + _render_chunk_md(chunk, context_name, include_header=True))
    return results


def format_diff_digest_markdown(
    context_name: str,
    diff: SnapshotDiff,
    chunks: List[Chunk],
) -> Union[str, List[str]]:
    added = len(diff.added)
    removed = len(diff.removed)
    modified = len(diff.modified)
    header = (
        f"# Diff Digest: {context_name}\n"
        f"## From: {diff.from_timestamp or 'initial'} → To: {diff.to_timestamp}\n"
        f"## Changes: +{added} added, -{removed} removed, ~{modified} modified\n\n"
    )

    if not chunks:
        return header + "_No changes._\n"

    multi_chunk = len(chunks) > 1
    if not multi_chunk:
        body = _render_chunk_md(chunks[0], context_name, include_header=False)
        return header + body

    results = []
    for chunk in chunks:
        chunk_header = (
            f"# Diff Digest: {context_name} [Chunk {chunk.index}/{chunk.total}]\n"
            f"## Changes: +{added} added, -{removed} removed, ~{modified} modified\n\n"
        )
        results.append(chunk_header + _render_chunk_md(chunk, context_name, include_header=True))
    return results


# ─── XML format ───────────────────────────────────────────────────────────────

def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_digest_xml(
    context_name: str,
    snapshot: Snapshot,
    files_content: List[FileContent],
    chunks: List[Chunk],
) -> Union[str, List[str]]:
    ts = snapshot.timestamp
    total_tokens = sum(f.tokens for f in files_content)
    multi_chunk = len(chunks) > 1

    def render_chunk(chunk: Chunk) -> str:
        parts = [f'<chuck context="{context_name}" snapshot="{ts}" '
                 f'total_files="{len(files_content)}" total_tokens="{total_tokens}"']
        if multi_chunk:
            parts[0] += f' chunk="{chunk.index}/{chunk.total}"'
        parts[0] += ">\n"
        for fc in chunk.files:
            parts.append(
                f'  <file path="{fc.path}" tokens="{fc.tokens}">\n'
                f"    <content><![CDATA[{fc.content}]]></content>\n"
                f"  </file>\n"
            )
        parts.append("</chuck>")
        return "".join(parts)

    if not multi_chunk:
        return render_chunk(chunks[0]) if chunks else f'<chuck context="{context_name}" snapshot="{ts}"/>'

    return [render_chunk(c) for c in chunks]


# ─── JSON format ──────────────────────────────────────────────────────────────

def format_digest_json(
    context_name: str,
    snapshot: Snapshot,
    files_content: List[FileContent],
    chunks: List[Chunk],
) -> Union[str, List[str]]:
    ts = snapshot.timestamp
    total_tokens = sum(f.tokens for f in files_content)
    multi_chunk = len(chunks) > 1

    def render_chunk(chunk: Chunk) -> str:
        data = {
            "context": context_name,
            "snapshot": ts,
            "files": [
                {
                    "path": fc.path,
                    "tokens": fc.tokens,
                    "content": fc.content,
                }
                for fc in chunk.files
            ],
            "meta": {
                "total_files": len(files_content),
                "total_tokens": total_tokens,
            },
        }
        if multi_chunk:
            data["chunk"] = chunk.index
            data["total_chunks"] = chunk.total
        return json.dumps(data, indent=2, ensure_ascii=False)

    if not multi_chunk:
        return render_chunk(chunks[0]) if chunks else json.dumps({
            "context": context_name, "snapshot": ts, "files": [], "meta": {"total_files": 0, "total_tokens": 0}
        }, indent=2)

    return [render_chunk(c) for c in chunks]


# ─── Diff digest formatters ───────────────────────────────────────────────────

def _diff_file_contents(
    diff: SnapshotDiff,
    root: Optional[Path],
    token_counter: Optional[Callable],
) -> List[FileContent]:
    """Build FileContent entries for all changed files in the diff."""
    contents = []

    for fd in diff.added:
        abs_path = str(root / fd.path) if root else fd.path
        content = _read_safe(abs_path)
        tokens = count_tokens(content, token_counter)
        contents.append(FileContent(
            path=fd.path, content=content, tokens=tokens, is_changed=True
        ))

    for fd in diff.modified:
        abs_path = str(root / fd.path) if root else fd.path
        content = _read_safe(abs_path)
        tokens = count_tokens(content, token_counter)
        display = content
        display_tokens = tokens
        contents.append(FileContent(
            path=fd.path, content=display, tokens=display_tokens, is_changed=True
        ))

    for fd in diff.removed:
        contents.append(FileContent(
            path=fd.path,
            content=f"[FILE REMOVED]\nPrevious hash: {fd.old_hash}\nPrevious tokens: {fd.old_tokens}",
            tokens=10,
            is_changed=True,
        ))

    return contents


# ─── Main entry points ────────────────────────────────────────────────────────

def build_digest(
    context_name: str,
    snapshot: Snapshot,
    root: Optional[Path] = None,
    token_budget: Optional[int] = None,
    format: str = "markdown",
    token_counter: Optional[Callable[[str], int]] = None,
) -> Union[str, List[str]]:
    """Build a full digest of a context from a snapshot."""
    files_content = []
    for rel_path, rec in snapshot.files.items():
        abs_path = rec.abs_path or (str(root / rel_path) if root else rel_path)
        content = _read_safe(abs_path)
        tokens = count_tokens(content, token_counter)
        files_content.append(FileContent(path=rel_path, content=content, tokens=tokens))

    counter = token_counter or (lambda t: count_tokens(t))

    if token_budget and token_budget > 0:
        chunks = chunk_files(files_content, token_budget, counter)
    else:
        # Single chunk with everything
        from .chunker import Chunk
        single = Chunk(index=1, total=1, files=files_content)
        chunks = [single]

    if format == "xml":
        return format_digest_xml(context_name, snapshot, files_content, chunks)
    elif format == "json":
        return format_digest_json(context_name, snapshot, files_content, chunks)
    else:
        return format_digest_markdown(context_name, snapshot, files_content, chunks)


def build_diff_digest(
    context_name: str,
    diff: SnapshotDiff,
    snapshot: Snapshot,
    root: Optional[Path] = None,
    token_budget: Optional[int] = None,
    format: str = "markdown",
    token_counter: Optional[Callable[[str], int]] = None,
) -> Union[str, List[str]]:
    """Build a digest of only what changed since the last snapshot."""
    files_content = _diff_file_contents(diff, root, token_counter)
    counter = token_counter or (lambda t: count_tokens(t))

    if token_budget and token_budget > 0:
        chunks = chunk_files(files_content, token_budget, counter, prioritize_changed=True)
    else:
        from .chunker import Chunk
        if files_content:
            single = Chunk(index=1, total=1, files=files_content)
            chunks = [single]
        else:
            chunks = []

    if format == "xml":
        # Reuse snapshot format with diff header comment
        result = format_digest_xml(context_name, snapshot, files_content, chunks)
        return result
    elif format == "json":
        result = format_digest_json(context_name, snapshot, files_content, chunks)
        return result
    else:
        return format_diff_digest_markdown(context_name, diff, chunks)
