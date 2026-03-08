"""
Basic Chuck usage — simplest possible workflow.

Run from the project root:
    python examples/basic_usage.py
"""

import tempfile
import textwrap
from pathlib import Path

import chuck


def main():
    # Create a temporary project to demo on
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Create some sample files
        src = root / "src"
        src.mkdir()
        (src / "main.py").write_text(textwrap.dedent("""\
            def main():
                print("Hello, Chuck!")

            if __name__ == "__main__":
                main()
        """))
        (src / "utils.py").write_text(textwrap.dedent("""\
            def add(a, b):
                return a + b
        """))

        # --- Chuck workflow ---

        # 1. Initialize
        c = chuck.init(str(root))
        print("Initialized Chuck at:", root)

        # 2. Define a context
        c.context("src", ["src/**/*.py"])
        print("Defined context 'src'")

        # 3. Take a snapshot
        snap = c.snapshot("src")
        print(f"Snapshot taken: {snap.file_count} files, {snap.total_tokens} tokens")

        # 4. Get a digest
        digest = c.digest("src")
        print("\n--- Digest (markdown) ---")
        print(digest[:500] + "..." if len(digest) > 500 else digest)

        # 5. Simulate a change
        (src / "main.py").write_text(textwrap.dedent("""\
            def main():
                print("Hello, improved Chuck!")

            if __name__ == "__main__":
                main()
        """))

        # 6. Check diff
        diff = c.diff("src")
        print(f"\nChanged since snapshot: {len(diff.modified)} files modified")

        # 7. Get diff digest (only what changed)
        diff_digest = c.diff_digest("src")
        print("\n--- Diff Digest ---")
        print(diff_digest[:400] + "..." if len(diff_digest) > 400 else diff_digest)

        # 8. Status
        status = c.status("src")
        print(f"\nStatus: {status['file_count']} files, last snapshot: {status['last_snapshot']}")


if __name__ == "__main__":
    main()
