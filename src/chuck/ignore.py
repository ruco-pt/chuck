"""Gitignore-style pattern matching for .chuckignore files."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import List, Optional

# Default patterns always applied
DEFAULT_PATTERNS = [
    ".git/",
    ".chuck/",
    "node_modules/",
    "__pycache__/",
    "*.pyc",
    ".env",
    ".env.*",
]


def _pattern_to_regex(pattern: str) -> Optional[re.Pattern]:
    """Convert a gitignore-style pattern to a compiled regex."""
    pattern = pattern.strip()
    if not pattern or pattern.startswith("#"):
        return None

    negated = pattern.startswith("!")
    if negated:
        pattern = pattern[1:]

    # Directory-only pattern
    dir_only = pattern.endswith("/")
    if dir_only:
        pattern = pattern.rstrip("/")

    # Anchor to root if pattern contains a slash (excluding trailing)
    anchored = "/" in pattern

    # Convert gitignore glob to regex
    # ** matches any path segment
    parts = []
    i = 0
    while i < len(pattern):
        if pattern[i:i+3] == "**/":
            parts.append("(?:.+/)?")
            i += 3
        elif pattern[i:i+2] == "**":
            parts.append(".+")
            i += 2
        elif pattern[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            parts.append("[^/]")
            i += 1
        elif pattern[i] in ".^$+{}[]|()":
            parts.append(re.escape(pattern[i]))
            i += 1
        else:
            parts.append(pattern[i])
            i += 1

    regex_body = "".join(parts)

    if anchored:
        regex_str = f"^{regex_body}(/.*)?$"
    else:
        regex_str = f"(?:^|/){regex_body}(/.*)?$"

    try:
        return re.compile(regex_str)
    except re.error:
        return None


class IgnoreFilter:
    """Apply gitignore-style patterns to filter file paths."""

    def __init__(self, patterns: List[str] = None, root: Path = None):
        self.root = root or Path(".")
        self._rules: List[tuple[re.Pattern, bool]] = []  # (pattern, negated)
        for p in (DEFAULT_PATTERNS + (patterns or [])):
            self._add_pattern(p)

    def _add_pattern(self, pattern: str):
        pattern = pattern.strip()
        if not pattern or pattern.startswith("#"):
            return
        negated = pattern.startswith("!")
        if negated:
            pattern = pattern[1:]
        rx = _pattern_to_regex(pattern)
        if rx:
            self._rules.append((rx, negated))

    @classmethod
    def from_file(cls, path: Path, extra_patterns: List[str] = None, root: Path = None) -> "IgnoreFilter":
        patterns = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                patterns.append(line)
        if extra_patterns:
            patterns.extend(extra_patterns)
        return cls(patterns=patterns, root=root or path.parent)

    def is_ignored(self, path: Path) -> bool:
        """Return True if the path should be ignored."""
        try:
            rel = path.relative_to(self.root)
        except ValueError:
            rel = path

        rel_str = rel.as_posix()

        matched = False
        for rx, negated in self._rules:
            if rx.search(rel_str):
                matched = not negated

        return matched

    def filter(self, paths: List[Path]) -> List[Path]:
        """Return paths that are NOT ignored."""
        return [p for p in paths if not self.is_ignored(p)]
