"""
Chuck + Claude Code integration pattern.

This shows how to use Chuck's output with any LLM CLI tool.
In practice: chuck digest src | claude "review this code"

This example simulates the pattern without requiring a real API key.
"""

import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import chuck


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Create a sample project
        src = root / "src"
        src.mkdir()
        (src / "auth.py").write_text(textwrap.dedent("""\
            import hashlib

            # WARNING: This is example code with intentional issues for demo purposes
            def hash_password(password: str) -> str:
                # Weak hashing — should use bcrypt/argon2
                return hashlib.md5(password.encode()).hexdigest()

            def verify_password(password: str, hashed: str) -> bool:
                return hash_password(password) == hashed

            # SQL injection risk in next function
            def get_user(db, username: str):
                query = f"SELECT * FROM users WHERE username = '{username}'"
                return db.execute(query)
        """))

        # Initialize and snapshot
        c = chuck.init(str(root))
        c.context("src", ["src/**/*.py"])
        c.snapshot("src")

        # Get markdown digest
        digest = c.digest("src", format="markdown")

        print("=== Chuck Digest Output ===")
        print(digest)
        print()
        print("=== How to pipe to Claude ===")
        print("In your shell:")
        print()
        print("  # Full review:")
        print("  chuck digest src | claude 'review this code for security issues'")
        print()
        print("  # After making changes:")
        print("  chuck diff-digest src | claude 'review only the changes I made'")
        print()
        print("  # With token budget:")
        print("  chuck digest src --budget 4000 | claude 'summarize this codebase'")
        print()

        # Show XML format (good for structured LLM consumption)
        xml_digest = c.digest("src", format="xml")
        print("=== XML Format (for structured consumption) ===")
        print(xml_digest)


if __name__ == "__main__":
    main()
