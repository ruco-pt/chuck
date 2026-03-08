"""Snapshot creation, storage, and diffing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .hasher import hash_file
from .tokens import count_tokens


@dataclass
class FileRecord:
    """Metadata record for a single file in a snapshot."""
    path: str          # relative to project root
    abs_path: str      # absolute path (not stored in snapshot JSON)
    size: int
    hash: str
    modified: float
    tokens: int

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "size": self.size,
            "hash": self.hash,
            "modified": self.modified,
            "tokens": self.tokens,
        }

    @classmethod
    def from_dict(cls, data: dict, root: Path) -> "FileRecord":
        return cls(
            path=data["path"],
            abs_path=str(root / data["path"]),
            size=data.get("size", 0),
            hash=data.get("hash", ""),
            modified=data.get("modified", 0.0),
            tokens=data.get("tokens", 0),
        )


@dataclass
class Snapshot:
    """A point-in-time record of a context's files."""
    context_name: str
    timestamp: str
    files: Dict[str, FileRecord] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return sum(f.tokens for f in self.files.values())

    @property
    def file_count(self) -> int:
        return len(self.files)

    def to_dict(self) -> dict:
        return {
            "context": self.context_name,
            "timestamp": self.timestamp,
            "files": {k: v.to_dict() for k, v in self.files.items()},
        }

    @classmethod
    def from_dict(cls, data: dict, root: Path) -> "Snapshot":
        snap = cls(
            context_name=data["context"],
            timestamp=data["timestamp"],
        )
        for rel_path, fdata in data.get("files", {}).items():
            rec = FileRecord.from_dict({"path": rel_path, **fdata}, root)
            snap.files[rel_path] = rec
        return snap

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path, root: Path) -> "Snapshot":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data, root)


@dataclass
class FileDiff:
    """Diff information for a single file."""
    path: str
    status: str  # "added" | "removed" | "modified"
    old_hash: str = ""
    new_hash: str = ""
    old_tokens: int = 0
    new_tokens: int = 0

    def tokens_delta(self) -> int:
        return self.new_tokens - self.old_tokens


@dataclass
class SnapshotDiff:
    """Diff between two snapshots (or a snapshot and current state)."""
    context_name: str
    from_timestamp: Optional[str]
    to_timestamp: Optional[str]
    added: List[FileDiff] = field(default_factory=list)
    removed: List[FileDiff] = field(default_factory=list)
    modified: List[FileDiff] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.modified)

    @property
    def changed_files(self) -> List[FileDiff]:
        return self.added + self.removed + self.modified

    @property
    def tokens_changed(self) -> int:
        total = 0
        for f in self.added:
            total += f.new_tokens
        for f in self.removed:
            total -= f.old_tokens
        for f in self.modified:
            total += f.tokens_delta()
        return total


def _read_file_safe(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except (OSError, IOError):
        return ""


def build_snapshot(
    context_name: str,
    files: List[Path],
    root: Path,
    token_counter: Optional[Callable[[str], int]] = None,
    token_cache: Optional[Dict[str, int]] = None,
) -> Snapshot:
    """Build a new Snapshot from a list of resolved file paths."""
    timestamp = datetime.now(timezone.utc).isoformat()
    snap = Snapshot(context_name=context_name, timestamp=timestamp)

    cache = token_cache if token_cache is not None else {}

    for abs_path in files:
        try:
            rel = abs_path.relative_to(root)
        except ValueError:
            rel = abs_path
        rel_str = rel.as_posix()

        file_hash = hash_file(abs_path)
        stat = abs_path.stat()

        # Token count from cache if hash unchanged
        if file_hash and file_hash in cache:
            tokens = cache[file_hash]
        else:
            content = _read_file_safe(str(abs_path))
            tokens = count_tokens(content, token_counter)
            if file_hash:
                cache[file_hash] = tokens

        snap.files[rel_str] = FileRecord(
            path=rel_str,
            abs_path=str(abs_path),
            size=stat.st_size,
            hash=file_hash,
            modified=stat.st_mtime,
            tokens=tokens,
        )

    return snap


def diff_snapshots(
    context_name: str,
    from_snap: Optional[Snapshot],
    to_snap: Snapshot,
    root: Path,
) -> SnapshotDiff:
    """Compare two snapshots and return a structured diff."""
    diff = SnapshotDiff(
        context_name=context_name,
        from_timestamp=from_snap.timestamp if from_snap else None,
        to_timestamp=to_snap.timestamp,
    )

    old_files = dict(from_snap.files) if from_snap else {}
    new_files = dict(to_snap.files)

    old_keys = set(old_files)
    new_keys = set(new_files)

    for path in sorted(new_keys - old_keys):
        rec = new_files[path]
        diff.added.append(FileDiff(
            path=path,
            status="added",
            new_hash=rec.hash,
            new_tokens=rec.tokens,
        ))

    for path in sorted(old_keys - new_keys):
        rec = old_files[path]
        diff.removed.append(FileDiff(
            path=path,
            status="removed",
            old_hash=rec.hash,
            old_tokens=rec.tokens,
        ))

    for path in sorted(old_keys & new_keys):
        old = old_files[path]
        new = new_files[path]
        if old.hash != new.hash:
            fd = FileDiff(
                path=path,
                status="modified",
                old_hash=old.hash,
                new_hash=new.hash,
                old_tokens=old.tokens,
                new_tokens=new.tokens,
            )
            diff.modified.append(fd)

    return diff
