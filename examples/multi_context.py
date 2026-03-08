"""
Multi-context Chuck usage — tracking different project areas separately.

This pattern lets you maintain separate token budgets and change tracking
for different concerns (backend, frontend, docs, tests).
"""

import tempfile
import textwrap
from pathlib import Path

import chuck


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Create a project with multiple concerns
        for d in ["api", "models", "components", "docs", "tests"]:
            (root / "src" / d).mkdir(parents=True)

        (root / "src" / "api" / "routes.py").write_text("# API routes\ndef get_users(): pass\n")
        (root / "src" / "api" / "auth.py").write_text("# Auth logic\ndef login(): pass\n")
        (root / "src" / "models" / "user.py").write_text("# User model\nclass User: pass\n")
        (root / "src" / "components" / "App.jsx").write_text("// React App\nexport default function App() {}\n")
        (root / "src" / "components" / "Button.jsx").write_text("// Button component\nexport function Button() {}\n")
        (root / "docs" / "api.md").mkdir(parents=True) if False else None
        (root / "docs").mkdir(exist_ok=True)
        (root / "docs" / "api.md").write_text("# API Documentation\n\nEndpoints...\n")
        (root / "docs" / "setup.md").write_text("# Setup Guide\n\nInstall...\n")

        # Initialize Chuck
        c = chuck.init(str(root))

        # Define separate contexts
        c.context("backend", ["src/api/**/*.py", "src/models/**/*.py"])
        c.context("frontend", ["src/components/**/*.jsx"])
        c.context("docs", ["docs/**/*.md"])

        print("Defined 3 contexts:", c.contexts())

        # Snapshot all contexts
        for name in c.contexts():
            snap = c.snapshot(name)
            print(f"  {name}: {snap.file_count} files, {snap.total_tokens} tokens")

        # Get status for all
        print("\n--- Status ---")
        status = c.status()
        for name, info in status.items():
            print(f"  {name}: {info['file_count']} files, {info['total_tokens']} tokens")

        # Digest backend with a token budget
        print("\n--- Backend Digest (budget=200 tokens) ---")
        result = c.digest("backend", token_budget=200)
        if isinstance(result, list):
            print(f"  Chunked into {len(result)} chunks")
            print(result[0][:300] + "...")
        else:
            print(result[:300] + "..." if len(result) > 300 else result)

        # Simulate a backend change
        (root / "src" / "api" / "routes.py").write_text(
            "# API routes\ndef get_users(): return []\ndef create_user(): pass\n"
        )

        # diff-digest shows only what changed in backend
        print("\n--- Backend Diff Digest ---")
        diff_d = c.diff_digest("backend")
        print(diff_d[:400] + "..." if len(diff_d) > 400 else diff_d)

        # Frontend has no changes
        frontend_diff = c.diff("frontend")
        print(f"\nFrontend changes: {frontend_diff.has_changes}")


if __name__ == "__main__":
    main()
