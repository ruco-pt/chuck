"""
Chuck in CI/CD — context-aware code review for pipelines.

Pattern: On each PR or commit, produce a diff-digest of only what changed.
This lets an AI reviewer focus on the delta rather than the whole codebase.

Usage in CI (GitHub Actions, etc.):
    python examples/ci_pipeline.py

Or inline in a workflow step:
    chuck snap src
    # ... CI runs tests, builds, etc. ...
    chuck diff-digest src --format json > /tmp/chuck_diff.json
    cat /tmp/chuck_diff.json | your-ai-review-tool
"""

import json
import sys
import tempfile
import textwrap
from pathlib import Path

import chuck


def simulate_ci_run():
    """Simulate a CI pipeline with before/after snapshots."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        src.mkdir()

        # Initial state (as if checking out a branch)
        (src / "api.py").write_text(textwrap.dedent("""\
            def get_items():
                return []

            def create_item(name: str):
                return {"name": name}
        """))
        (src / "db.py").write_text(textwrap.dedent("""\
            class Database:
                def connect(self):
                    pass
        """))

        c = chuck.init(str(root))
        c.context("src", ["src/**/*.py"])

        # --- Step 1: Snapshot at start of CI ---
        print("[CI] Taking baseline snapshot...")
        snap = c.snapshot("src")
        print(f"[CI] Baseline: {snap.file_count} files, {snap.total_tokens} tokens")

        # Simulate developer changes during CI build
        (src / "api.py").write_text(textwrap.dedent("""\
            from .db import Database

            def get_items():
                db = Database()
                return db.query_all()

            def create_item(name: str, description: str = ""):
                db = Database()
                return db.insert({"name": name, "description": description})

            def delete_item(item_id: int):
                db = Database()
                db.delete(item_id)
        """))
        # New file added
        (src / "validators.py").write_text(textwrap.dedent("""\
            def validate_name(name: str) -> bool:
                return bool(name) and len(name) <= 255

            def validate_id(item_id: int) -> bool:
                return item_id > 0
        """))

        # --- Step 2: Diff to see what changed ---
        diff = c.diff("src")
        print(f"\n[CI] Changes detected:")
        print(f"  Added: {len(diff.added)} files")
        print(f"  Modified: {len(diff.modified)} files")
        print(f"  Removed: {len(diff.removed)} files")
        print(f"  Token delta: {diff.tokens_changed:+d}")

        if not diff.has_changes:
            print("[CI] No changes — skipping AI review step")
            return 0

        # --- Step 3: Generate diff-digest for AI review ---
        print("\n[CI] Generating diff-digest for AI review...")
        diff_digest_json = c.diff_digest("src", format="json", token_budget=8000)

        if isinstance(diff_digest_json, list):
            # Multiple chunks — review each
            reviews = []
            for i, chunk in enumerate(diff_digest_json):
                data = json.loads(chunk)
                print(f"[CI] Chunk {i+1}/{len(diff_digest_json)}: {len(data['files'])} files")
                reviews.append(f"Chunk {i+1}: {[f['path'] for f in data['files']]}")
            print("\n[CI] Would send each chunk to AI reviewer:")
            for r in reviews:
                print(f"  {r}")
        else:
            data = json.loads(diff_digest_json)
            print(f"[CI] Diff digest: {len(data['files'])} changed files")
            print("[CI] Would pipe to: your-ai-review-tool --context diff")

        # Show the markdown diff for human readability
        print("\n[CI] Markdown diff-digest (for PR comment):")
        diff_md = c.diff_digest("src", format="markdown")
        print(diff_md[:600] + "..." if len(diff_md) > 600 else diff_md)

        print("\n[CI] Pipeline complete. Chuck diff-digest ready for AI review.")
        return 0


if __name__ == "__main__":
    sys.exit(simulate_ci_run())
