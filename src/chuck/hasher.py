"""File hashing utilities."""

from __future__ import annotations

import hashlib
from pathlib import Path


def hash_file(path: Path, algorithm: str = "sha256") -> str:
    """Return hex digest of a file's contents."""
    h = hashlib.new(algorithm)
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except (OSError, IOError):
        return ""
    return h.hexdigest()


def hash_string(text: str) -> str:
    """Return SHA256 hex digest of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
