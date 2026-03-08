"""Chuck CLI — command-line interface."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional


def _find_root_from(start: Path) -> Path:
    """Walk up from start looking for .chuck/."""
    for parent in [start, *start.parents]:
        if (parent / ".chuck").exists():
            return parent
    return start


def _get_chuck(path: Optional[str] = None):
    from .core import Chuck
    if path:
        root = Path(path).resolve()
    else:
        root = _find_root_from(Path.cwd())
    if not (root / ".chuck").exists():
        print(f"No .chuck/ found. Run: chuck init", file=sys.stderr)
        sys.exit(1)
    return Chuck(root)


def _print_result(result):
    """Print string or list of strings (chunks) to stdout."""
    if isinstance(result, list):
        print("\n\n---\n\n".join(result))
    else:
        print(result)


# ─── Command handlers ─────────────────────────────────────────────────────────

def cmd_init(args):
    from .core import Chuck
    path = getattr(args, "path", None) or "."
    Chuck.init(path)
    print(f"Initialized .chuck/ in {Path(path).resolve()}")


def cmd_snap(args):
    c = _get_chuck(getattr(args, "path", None))
    quiet = args.quiet
    result = c.snap(quiet=quiet, format=args.format, budget=args.budget)
    if not quiet and result is not None:
        _print_result(result)
    elif quiet:
        snap = c._latest_snapshot()
        if snap:
            print(
                f"Snapped: {snap.file_count} files, {snap.total_tokens:,} tokens",
                file=sys.stderr,
            )


def cmd_patch(args):
    c = _get_chuck(getattr(args, "path", None))
    quiet = args.quiet
    result, auto_snapped = c.patch(quiet=quiet, format=args.format, budget=args.budget)
    if auto_snapped:
        print(
            "auto-snapped: diff exceeded threshold. new baseline set.",
            file=sys.stderr,
        )
    if not quiet and result is not None:
        _print_result(result)


def cmd_diff(args):
    from .core import NoSnapshotError
    c = _get_chuck(getattr(args, "path", None))
    try:
        diff = c.diff()
    except NoSnapshotError:
        print("No snapshot. Run: chuck snap", file=sys.stderr)
        sys.exit(1)

    if args.json:
        data = {
            "from": diff.from_timestamp,
            "to": diff.to_timestamp,
            "has_changes": diff.has_changes,
            "added": [{"path": f.path, "tokens": f.new_tokens} for f in diff.added],
            "removed": [{"path": f.path, "tokens": f.old_tokens} for f in diff.removed],
            "modified": [
                {"path": f.path, "old_tokens": f.old_tokens, "new_tokens": f.new_tokens}
                for f in diff.modified
            ],
        }
        print(json.dumps(data, indent=2))
        return

    if not diff.has_changes:
        print("No changes since last snap.")
        return

    if diff.added:
        print(f"Added ({len(diff.added)}):")
        for f in diff.added:
            print(f"  + {f.path} ({f.new_tokens} tokens)")

    if diff.removed:
        print(f"Removed ({len(diff.removed)}):")
        for f in diff.removed:
            print(f"  - {f.path} ({f.old_tokens} tokens)")

    if diff.modified:
        print(f"Modified ({len(diff.modified)}):")
        for f in diff.modified:
            delta = f.tokens_delta()
            sign = "+" if delta >= 0 else ""
            print(f"  ~ {f.path} ({sign}{delta} tokens)")

    total_delta = diff.tokens_changed
    sign = "+" if total_delta >= 0 else ""
    print(f"\nTotal token delta: {sign}{total_delta}")


def cmd_status(args):
    c = _get_chuck(getattr(args, "path", None))
    status = c.status()

    print(f"\nChuck: {status['root']}")
    print(f"  Files:     {status['file_count']}")
    print(f"  Tokens:    {status['total_tokens']:,}")
    print(f"  Snapshots: {status['snapshot_count']}")
    print(f"  Last snap: {status['last_snapshot'] or 'never'}")
    if status["changes_since_snap"]:
        changes = status["changes_since_snap"]
        delta = changes["tokens_delta"]
        sign = "+" if delta >= 0 else ""
        print(
            f"  Changed:   {changes['files']} files, {sign}{delta} tokens since last snap"
        )


def cmd_ls(args):
    from .core import Chuck
    path = getattr(args, "path", None) or "."
    instances = Chuck.ls(path)
    if not instances:
        print("No Chuck instances found.")
        return
    for p in instances:
        print(p)


def cmd_reset(args):
    c = _get_chuck(getattr(args, "path", None))
    c.reset()
    print(f"Reset: cleared snapshots for {c.root}")


def cmd_integrate(args):
    from .core import ChuckError
    c = _get_chuck(getattr(args, "path", None))
    try:
        written = c.integrate(args.agent)
    except ChuckError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    for key, fpath in written.items():
        print(f"Written: {fpath}")


# ─── Argument parser ──────────────────────────────────────────────────────────

def build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="chuck",
        description="Chuck — context pre-processor for agents and humans.",
    )
    parser.add_argument("--version", action="version", version="chuck 1.0.0")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # init
    p_init = sub.add_parser("init", help="Initialize .chuck/ in a directory")
    p_init.add_argument(
        "path", nargs="?", default=".", help="Directory to initialize (default: .)"
    )
    p_init.set_defaults(func=cmd_init)

    # snap
    p_snap = sub.add_parser(
        "snap", help="Full baseline snapshot — saves and emits to stdout"
    )
    p_snap.add_argument(
        "path", nargs="?", default=None, help="Directory (default: current)"
    )
    p_snap.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress stdout output"
    )
    p_snap.add_argument(
        "--format",
        choices=["markdown", "xml", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    p_snap.add_argument(
        "--budget", type=int, default=None, help="Token budget per chunk"
    )
    p_snap.set_defaults(func=cmd_snap)

    # patch
    p_patch = sub.add_parser(
        "patch", help="Delta since last snap — emits to stdout, baseline unchanged"
    )
    p_patch.add_argument(
        "path", nargs="?", default=None, help="Directory (default: current)"
    )
    p_patch.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress stdout output"
    )
    p_patch.add_argument(
        "--format",
        choices=["markdown", "xml", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    p_patch.add_argument(
        "--budget", type=int, default=None, help="Token budget per chunk"
    )
    p_patch.set_defaults(func=cmd_patch)

    # diff
    p_diff = sub.add_parser(
        "diff", help="Show change summary (files/tokens) without emitting content"
    )
    p_diff.add_argument(
        "path", nargs="?", default=None, help="Directory (default: current)"
    )
    p_diff.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )
    p_diff.set_defaults(func=cmd_diff)

    # status
    p_status = sub.add_parser("status", help="Show instance metadata")
    p_status.add_argument(
        "path", nargs="?", default=None, help="Directory (default: current)"
    )
    p_status.set_defaults(func=cmd_status)

    # ls
    p_ls = sub.add_parser(
        "ls", help="List all Chuck instances found under a path"
    )
    p_ls.add_argument(
        "path", nargs="?", default=None, help="Root path to search (default: .)"
    )
    p_ls.set_defaults(func=cmd_ls)

    # reset
    p_reset = sub.add_parser("reset", help="Clear snapshot history")
    p_reset.add_argument(
        "path", nargs="?", default=None, help="Directory (default: current)"
    )
    p_reset.set_defaults(func=cmd_reset)

    # integrate
    p_integrate = sub.add_parser(
        "integrate", help="Generate agent-specific integration files"
    )
    p_integrate.add_argument(
        "agent",
        choices=["claude", "goose", "agents", "kilo"],
        help="Agent to integrate with",
    )
    p_integrate.add_argument(
        "path", nargs="?", default=None, help="Directory (default: current)"
    )
    p_integrate.set_defaults(func=cmd_integrate)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
