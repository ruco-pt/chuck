#!/usr/bin/env python3
"""chuck-aider — launch Aider pre-loaded with Chuck context.

Reads .chuck/state.json to decide whether to pass patch.md or a fresh
snap_context.md as a read-only context file to Aider, then exec()s into
the real aider binary.

When the patch is too large or absent, runs `chuck snap --budget N` and
writes the result to .chuck/snap_context.md, keeping the context within
the model's token limit.

Usage:
    chuck-aider [aider-args...]
    chuck-aider --model claude-sonnet-4-6

Environment:
    CHUCK_AIDER_PATCH_THRESHOLD  Max changed-file count before falling back
                                 to a fresh snap (default: 20).
    CHUCK_AIDER_BUDGET           Token budget for snap fallback (default: 100000).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_PATCH_THRESHOLD = 20       # files changed before falling back to snap
DEFAULT_PATCH_WORD_THRESHOLD = 2000  # words in patch.md before using snap
DEFAULT_SNAP_BUDGET = 100_000      # token budget for snap fallback


# ─── Helpers ──────────────────────────────────────────────────────────────────

def find_chuck_root(start: Path) -> Path | None:
    """Walk up from *start* looking for a .chuck/ directory.

    Returns the directory that owns .chuck/, or None if not found.
    """
    for p in [start, *start.parents]:
        if (p / ".chuck").exists():
            return p
    return None


def load_state(chuck_root: Path) -> dict:
    """Load .chuck/state.json.  Returns {} on missing or invalid JSON."""
    state_path = chuck_root / ".chuck" / "state.json"
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def generate_snap_context(chuck_root: Path, budget: int) -> str:
    """Run `chuck snap --budget N` and write the result to .chuck/snap_context.md.

    Returns the absolute path to the written file.
    Raises RuntimeError if chuck snap fails.
    """
    result = subprocess.run(
        ["chuck", "snap", "--budget", str(budget)],
        capture_output=True,
        text=True,
        cwd=chuck_root,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"chuck snap failed (exit {result.returncode}):\n{result.stderr.strip()}"
        )
    snap_path = chuck_root / ".chuck" / "snap_context.md"
    snap_path.write_text(result.stdout, encoding="utf-8")
    return str(snap_path)


def select_context(
    chuck_root: Path,
    state: dict,
    patch_word_threshold: int = DEFAULT_PATCH_WORD_THRESHOLD,
) -> tuple[str, str]:
    """Choose which Chuck artifact to hand to Aider.

    Decision order:
    1. If patch.md exists and changed-file count <= CHUCK_AIDER_PATCH_THRESHOLD
       and patch.md word count <= *patch_word_threshold* → patch.md
    2. Otherwise → generate .chuck/snap_context.md via `chuck snap --budget N`

    Returns:
        (context_type, absolute_path)
        context_type is 'patch' or 'snap'.
    """
    patch_threshold = int(
        os.environ.get("CHUCK_AIDER_PATCH_THRESHOLD", str(DEFAULT_PATCH_THRESHOLD))
    )
    snap_budget = int(
        os.environ.get("CHUCK_AIDER_BUDGET", str(DEFAULT_SNAP_BUDGET))
    )

    changed_count = state.get("changes_since_snap", {}).get("files", 0)
    patch_path = chuck_root / ".chuck" / "patch.md"

    if patch_path.exists() and changed_count <= patch_threshold:
        try:
            patch_content = patch_path.read_text(encoding="utf-8")
            if len(patch_content.split()) <= patch_word_threshold:
                return "patch", str(patch_path)
        except OSError:
            pass

    snap_path = generate_snap_context(chuck_root, snap_budget)
    return "snap", snap_path


def build_aider_args(context_path: str, extra_args: list) -> list:
    """Build the full aider argv list.

    Args:
        context_path: Absolute path to the Chuck file to read.
        extra_args:   Remaining arguments forwarded verbatim from the user.

    Returns:
        list starting with "aider" suitable for os.execvp().
    """
    return ["aider", "--read", context_path] + list(extra_args)


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    chuck_root = find_chuck_root(Path.cwd())
    if chuck_root is None:
        print(
            "chuck-aider: error: no .chuck/ directory found. Run: chuck init",
            file=sys.stderr,
        )
        sys.exit(1)

    state_path = chuck_root / ".chuck" / "state.json"
    if not state_path.exists():
        print(
            "chuck-aider: error: .chuck/state.json missing. Run: chuck snap",
            file=sys.stderr,
        )
        sys.exit(1)

    state = load_state(chuck_root)
    try:
        context_type, context_path = select_context(chuck_root, state)
    except RuntimeError as e:
        print(f"chuck-aider: error: {e}", file=sys.stderr)
        sys.exit(1)

    aider_args = build_aider_args(context_path, sys.argv[1:])

    print(f"chuck-aider: loading {context_type} → {context_path}")

    os.execvp("aider", aider_args)


if __name__ == "__main__":
    main()
