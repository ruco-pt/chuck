"""Context definition and file resolution."""

from __future__ import annotations

import glob as glob_module
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .ignore import IgnoreFilter


@dataclass
class ContextDef:
    """Definition of a named context: which files to track."""
    name: str
    paths: List[str]
    ignore: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "paths": self.paths,
            "ignore": self.ignore,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContextDef":
        return cls(
            name=data["name"],
            paths=data.get("paths", []),
            ignore=data.get("ignore", []),
        )

    def resolve_files(self, root: Path, chuckignore_path: Optional[Path] = None) -> List[Path]:
        """Resolve all file paths for this context, applying ignore rules."""
        ignore_filter = IgnoreFilter.from_file(
            chuckignore_path or root / ".chuckignore",
            extra_patterns=self.ignore,
            root=root,
        )

        collected: List[Path] = []
        seen = set()

        for pattern in self.paths:
            # Handle absolute vs relative patterns
            if os.path.isabs(pattern):
                abs_pattern = pattern
            else:
                abs_pattern = str(root / pattern)

            matches = glob_module.glob(abs_pattern, recursive=True)

            if not matches:
                # Try as a literal path
                p = Path(abs_pattern)
                if p.exists():
                    matches = [str(p)]

            for match_str in sorted(matches):
                match = Path(match_str).resolve()
                if match in seen:
                    continue
                seen.add(match)

                if match.is_file():
                    if not ignore_filter.is_ignored(match):
                        collected.append(match)
                elif match.is_dir():
                    for child in sorted(match.rglob("*")):
                        if child in seen:
                            continue
                        seen.add(child)
                        if child.is_file() and not ignore_filter.is_ignored(child):
                            collected.append(child)

        return sorted(collected)
