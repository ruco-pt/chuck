"""Unit tests for Chuck-Aider patch vs manifest context selection."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make root-level chuck_aider importable when running from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))
import chuck_aider


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def chuck_root(tmp_path):
    """A tmp directory with an empty .chuck/ folder."""
    (tmp_path / ".chuck").mkdir()
    return tmp_path


def write_state(chuck_root: Path, files_changed: int = 0) -> dict:
    state = {
        "last_snap": "2026-03-02T10:00:00Z",
        "files": 42,
        "tokens": 8432,
        "changes_since_snap": {"files": files_changed, "tokens_delta": 0},
        "paths": {
            "snap": ".chuck/manifest.json",
            "patch": ".chuck/patch.md",
        },
    }
    (chuck_root / ".chuck" / "state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )
    return state


# ─── select_context ───────────────────────────────────────────────────────────

class TestSelectContext:
    def test_uses_patch_when_few_changes(self, chuck_root):
        state = write_state(chuck_root, files_changed=3)
        (chuck_root / ".chuck" / "patch.md").write_text("small patch", encoding="utf-8")
        ctx_type, path = chuck_aider.select_context(chuck_root, state)
        assert ctx_type == "patch"
        assert path.endswith("patch.md")

    def test_uses_manifest_when_too_many_changes(self, chuck_root, monkeypatch):
        monkeypatch.delenv("CHUCK_AIDER_PATCH_THRESHOLD", raising=False)
        state = write_state(chuck_root, files_changed=21)
        (chuck_root / ".chuck" / "patch.md").write_text("lots of content", encoding="utf-8")
        ctx_type, path = chuck_aider.select_context(chuck_root, state)
        assert ctx_type == "manifest"
        assert path.endswith("manifest.json")

    def test_uses_patch_at_exact_default_threshold(self, chuck_root, monkeypatch):
        monkeypatch.delenv("CHUCK_AIDER_PATCH_THRESHOLD", raising=False)
        state = write_state(chuck_root, files_changed=20)
        (chuck_root / ".chuck" / "patch.md").write_text("content", encoding="utf-8")
        ctx_type, _ = chuck_aider.select_context(chuck_root, state)
        assert ctx_type == "patch"

    def test_uses_manifest_when_patch_absent(self, chuck_root):
        state = write_state(chuck_root, files_changed=2)
        # patch.md intentionally not created
        ctx_type, path = chuck_aider.select_context(chuck_root, state)
        assert ctx_type == "manifest"
        assert path.endswith("manifest.json")

    def test_uses_manifest_when_patch_too_large(self, chuck_root):
        state = write_state(chuck_root, files_changed=2)
        large = " ".join(["word"] * 2001)
        (chuck_root / ".chuck" / "patch.md").write_text(large, encoding="utf-8")
        ctx_type, _ = chuck_aider.select_context(chuck_root, state, patch_word_threshold=2000)
        assert ctx_type == "manifest"

    def test_uses_patch_at_exact_word_threshold(self, chuck_root):
        state = write_state(chuck_root, files_changed=2)
        content = " ".join(["word"] * 2000)
        (chuck_root / ".chuck" / "patch.md").write_text(content, encoding="utf-8")
        ctx_type, _ = chuck_aider.select_context(chuck_root, state, patch_word_threshold=2000)
        assert ctx_type == "patch"

    def test_env_var_lowers_threshold(self, chuck_root, monkeypatch):
        monkeypatch.setenv("CHUCK_AIDER_PATCH_THRESHOLD", "5")
        state = write_state(chuck_root, files_changed=6)
        (chuck_root / ".chuck" / "patch.md").write_text("content", encoding="utf-8")
        ctx_type, _ = chuck_aider.select_context(chuck_root, state)
        assert ctx_type == "manifest"

    def test_env_var_raises_threshold(self, chuck_root, monkeypatch):
        monkeypatch.setenv("CHUCK_AIDER_PATCH_THRESHOLD", "50")
        state = write_state(chuck_root, files_changed=40)
        (chuck_root / ".chuck" / "patch.md").write_text("content", encoding="utf-8")
        ctx_type, _ = chuck_aider.select_context(chuck_root, state)
        assert ctx_type == "patch"

    def test_env_var_at_exact_threshold(self, chuck_root, monkeypatch):
        monkeypatch.setenv("CHUCK_AIDER_PATCH_THRESHOLD", "5")
        state = write_state(chuck_root, files_changed=5)
        (chuck_root / ".chuck" / "patch.md").write_text("content", encoding="utf-8")
        ctx_type, _ = chuck_aider.select_context(chuck_root, state)
        assert ctx_type == "patch"

    def test_default_threshold_is_20(self, chuck_root, monkeypatch):
        monkeypatch.delenv("CHUCK_AIDER_PATCH_THRESHOLD", raising=False)
        # 20 files → should still use patch (threshold is <=)
        state = write_state(chuck_root, files_changed=20)
        (chuck_root / ".chuck" / "patch.md").write_text("content", encoding="utf-8")
        ctx_type, _ = chuck_aider.select_context(chuck_root, state)
        assert ctx_type == "patch"
        # 21 files → manifest
        state = write_state(chuck_root, files_changed=21)
        ctx_type, _ = chuck_aider.select_context(chuck_root, state)
        assert ctx_type == "manifest"

    def test_zero_changes_uses_patch(self, chuck_root):
        state = write_state(chuck_root, files_changed=0)
        (chuck_root / ".chuck" / "patch.md").write_text("minor fix", encoding="utf-8")
        ctx_type, _ = chuck_aider.select_context(chuck_root, state)
        assert ctx_type == "patch"

    def test_manifest_path_contains_manifest(self, chuck_root):
        state = write_state(chuck_root, files_changed=25)
        ctx_type, path = chuck_aider.select_context(chuck_root, state)
        assert ctx_type == "manifest"
        assert "manifest.json" in path

    def test_patch_path_is_absolute(self, chuck_root):
        state = write_state(chuck_root, files_changed=0)
        (chuck_root / ".chuck" / "patch.md").write_text("fix", encoding="utf-8")
        _, path = chuck_aider.select_context(chuck_root, state)
        assert Path(path).is_absolute()

    def test_empty_state_falls_back_to_manifest(self, chuck_root):
        # state.json missing changes_since_snap key → 0 changed files
        (chuck_root / ".chuck" / "patch.md").write_text("fix", encoding="utf-8")
        ctx_type, _ = chuck_aider.select_context(chuck_root, {})
        assert ctx_type == "patch"


# ─── find_chuck_root ──────────────────────────────────────────────────────────

class TestFindChuckRoot:
    def test_finds_root_in_current_dir(self, tmp_path):
        (tmp_path / ".chuck").mkdir()
        assert chuck_aider.find_chuck_root(tmp_path) == tmp_path

    def test_finds_root_in_parent(self, tmp_path):
        (tmp_path / ".chuck").mkdir()
        subdir = tmp_path / "sub" / "deep"
        subdir.mkdir(parents=True)
        assert chuck_aider.find_chuck_root(subdir) == tmp_path

    def test_returns_none_when_absent(self, tmp_path):
        assert chuck_aider.find_chuck_root(tmp_path) is None

    def test_nearest_root_wins(self, tmp_path):
        """When nested .chuck/ dirs exist, the nearest one wins."""
        (tmp_path / ".chuck").mkdir()
        inner = tmp_path / "inner"
        inner.mkdir()
        (inner / ".chuck").mkdir()
        assert chuck_aider.find_chuck_root(inner) == inner


# ─── load_state ───────────────────────────────────────────────────────────────

class TestLoadState:
    def test_loads_valid_state(self, chuck_root):
        write_state(chuck_root, files_changed=5)
        state = chuck_aider.load_state(chuck_root)
        assert state["changes_since_snap"]["files"] == 5

    def test_returns_empty_dict_when_missing(self, chuck_root):
        assert chuck_aider.load_state(chuck_root) == {}

    def test_returns_empty_dict_on_invalid_json(self, chuck_root):
        (chuck_root / ".chuck" / "state.json").write_text("not-json", encoding="utf-8")
        assert chuck_aider.load_state(chuck_root) == {}
