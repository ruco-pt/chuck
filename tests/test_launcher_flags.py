"""Unit tests for chuck-aider Aider flag construction and config generation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import chuck_aider
import chuck_aider_init


# ─── build_aider_args ─────────────────────────────────────────────────────────

class TestBuildAiderArgs:
    def test_basic_structure(self):
        args = chuck_aider.build_aider_args("/path/to/patch.md", [])
        assert args == ["aider", "--read", "/path/to/patch.md"]

    def test_starts_with_aider(self):
        args = chuck_aider.build_aider_args("/any/path.md", ["--model", "x"])
        assert args[0] == "aider"

    def test_read_flag_is_second(self):
        args = chuck_aider.build_aider_args("/any/path.md", [])
        assert args[1] == "--read"

    def test_context_path_is_third(self):
        args = chuck_aider.build_aider_args("/some/manifest.json", [])
        assert args[2] == "/some/manifest.json"

    def test_extra_args_appended(self):
        extra = ["--model", "claude-sonnet-4-6"]
        args = chuck_aider.build_aider_args("/path.md", extra)
        assert args[3:] == extra

    def test_multiple_extra_args(self):
        extra = ["--model", "gpt-4", "--no-stream", "--yes"]
        args = chuck_aider.build_aider_args("/path.md", extra)
        assert args == ["aider", "--read", "/path.md"] + extra

    def test_no_extra_args(self):
        args = chuck_aider.build_aider_args("/path.md", [])
        assert len(args) == 3

    def test_extra_args_not_mutated(self):
        extra = ["--model", "x"]
        original = list(extra)
        chuck_aider.build_aider_args("/p.md", extra)
        assert extra == original


# ─── write_aider_conf ─────────────────────────────────────────────────────────

class TestWriteAiderConf:
    @pytest.fixture()
    def chuck_root(self, tmp_path):
        (tmp_path / ".chuck").mkdir()
        return tmp_path

    def test_creates_aider_conf_yml(self, chuck_root):
        chuck_aider_init.write_aider_conf(chuck_root)
        assert (chuck_root / ".aider.conf.yml").exists()

    def test_contains_read_key(self, chuck_root):
        chuck_aider_init.write_aider_conf(chuck_root)
        content = (chuck_root / ".aider.conf.yml").read_text()
        assert "read:" in content

    def test_auto_commits_false(self, chuck_root):
        chuck_aider_init.write_aider_conf(chuck_root)
        content = (chuck_root / ".aider.conf.yml").read_text()
        assert "auto-commits: false" in content

    def test_gitignore_false(self, chuck_root):
        chuck_aider_init.write_aider_conf(chuck_root)
        content = (chuck_root / ".aider.conf.yml").read_text()
        assert "gitignore: false" in content

    def test_uses_patch_when_present(self, chuck_root):
        (chuck_root / ".chuck" / "patch.md").write_text("change summary", encoding="utf-8")
        chuck_aider_init.write_aider_conf(chuck_root)
        content = (chuck_root / ".aider.conf.yml").read_text()
        assert ".chuck/patch.md" in content

    def test_falls_back_to_manifest_when_patch_absent(self, chuck_root):
        chuck_aider_init.write_aider_conf(chuck_root)
        content = (chuck_root / ".aider.conf.yml").read_text()
        assert ".chuck/manifest.json" in content

    def test_falls_back_to_manifest_when_patch_empty(self, chuck_root):
        (chuck_root / ".chuck" / "patch.md").write_text("", encoding="utf-8")
        chuck_aider_init.write_aider_conf(chuck_root)
        content = (chuck_root / ".aider.conf.yml").read_text()
        assert ".chuck/manifest.json" in content

    def test_is_idempotent(self, chuck_root):
        chuck_aider_init.write_aider_conf(chuck_root)
        first = (chuck_root / ".aider.conf.yml").read_text()
        chuck_aider_init.write_aider_conf(chuck_root)
        second = (chuck_root / ".aider.conf.yml").read_text()
        assert first == second

    def test_returns_path(self, chuck_root):
        result = chuck_aider_init.write_aider_conf(chuck_root)
        assert isinstance(result, Path)
        assert result == chuck_root / ".aider.conf.yml"


# ─── update_gitignore ─────────────────────────────────────────────────────────

class TestUpdateGitignore:
    @pytest.fixture()
    def git_root(self, tmp_path):
        (tmp_path / ".chuck").mkdir()
        (tmp_path / ".git").mkdir()
        return tmp_path

    @pytest.fixture()
    def no_git_root(self, tmp_path):
        (tmp_path / ".chuck").mkdir()
        return tmp_path

    def test_creates_gitignore_in_git_repo(self, git_root):
        chuck_aider_init.update_gitignore(git_root)
        assert (git_root / ".gitignore").exists()

    def test_adds_aider_pattern(self, git_root):
        chuck_aider_init.update_gitignore(git_root)
        content = (git_root / ".gitignore").read_text()
        assert ".aider*" in content

    def test_adds_chuck_dir_pattern(self, git_root):
        chuck_aider_init.update_gitignore(git_root)
        content = (git_root / ".gitignore").read_text()
        assert ".chuck/" in content

    def test_skips_non_git_repo(self, no_git_root):
        chuck_aider_init.update_gitignore(no_git_root)
        assert not (no_git_root / ".gitignore").exists()

    def test_does_not_duplicate_existing_patterns(self, git_root):
        (git_root / ".gitignore").write_text(".aider*\n.chuck/\n", encoding="utf-8")
        chuck_aider_init.update_gitignore(git_root)
        content = (git_root / ".gitignore").read_text()
        assert content.count(".aider*") == 1
        assert content.count(".chuck/") == 1

    def test_appends_to_existing_gitignore(self, git_root):
        (git_root / ".gitignore").write_text("*.pyc\n__pycache__/\n", encoding="utf-8")
        chuck_aider_init.update_gitignore(git_root)
        content = (git_root / ".gitignore").read_text()
        assert "*.pyc" in content
        assert ".aider*" in content

    def test_idempotent(self, git_root):
        chuck_aider_init.update_gitignore(git_root)
        after_first = (git_root / ".gitignore").read_text()
        chuck_aider_init.update_gitignore(git_root)
        after_second = (git_root / ".gitignore").read_text()
        assert after_first == after_second


# ─── select_read_file ─────────────────────────────────────────────────────────

class TestSelectReadFile:
    @pytest.fixture()
    def chuck_root(self, tmp_path):
        (tmp_path / ".chuck").mkdir()
        return tmp_path

    def test_patch_when_present_and_non_empty(self, chuck_root):
        (chuck_root / ".chuck" / "patch.md").write_text("diff here", encoding="utf-8")
        assert chuck_aider_init.select_read_file(chuck_root) == ".chuck/patch.md"

    def test_manifest_when_patch_absent(self, chuck_root):
        assert chuck_aider_init.select_read_file(chuck_root) == ".chuck/manifest.json"

    def test_manifest_when_patch_empty(self, chuck_root):
        (chuck_root / ".chuck" / "patch.md").write_text("   \n", encoding="utf-8")
        assert chuck_aider_init.select_read_file(chuck_root) == ".chuck/manifest.json"
