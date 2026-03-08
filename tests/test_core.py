"""Tests for the Chuck orchestrator — directory-based model."""

import json
import pytest
from pathlib import Path
import chuck
from chuck.core import Chuck, NoSnapshotError, ChuckError


@pytest.fixture
def project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("def main():\n    print('hello')\n")
    (src / "utils.py").write_text("def helper():\n    return 42\n")
    (tmp_path / "README.md").write_text("# Project\n\nThis is the readme.\n")
    return tmp_path


@pytest.fixture
def c(project):
    return chuck.init(str(project))


# ─── init ─────────────────────────────────────────────────────────────────────

def test_init_creates_chuck_dir(project):
    c = chuck.init(str(project))
    assert (project / ".chuck").exists()
    assert (project / ".chuck" / "config.json").exists()
    assert (project / ".chuck" / "snapshots").exists()


def test_init_idempotent(project):
    chuck.init(str(project))
    chuck.init(str(project))
    assert (project / ".chuck").exists()


def test_init_default_config(project):
    c = chuck.init(str(project))
    config = json.loads((project / ".chuck" / "config.json").read_text())
    assert "settings" in config
    assert "auto_snap_threshold" in config["settings"]
    threshold = config["settings"]["auto_snap_threshold"]
    assert "files" in threshold
    assert "tokens" in threshold


# ─── snap ─────────────────────────────────────────────────────────────────────

def test_snap_creates_manifest(c, project):
    result = c.snap()
    assert (project / ".chuck" / "manifest.json").exists()
    assert result is not None


def test_snap_creates_snapshot_file(c, project):
    c.snap()
    snap_dir = project / ".chuck" / "snapshots"
    assert len(list(snap_dir.glob("*.json"))) == 1


def test_snap_updates_state(c, project):
    c.snap()
    state_path = project / ".chuck" / "state.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text())
    assert "last_snap" in state
    assert state["files"] > 0
    assert state["changes_since_snap"]["files"] == 0
    assert state["changes_since_snap"]["tokens_delta"] == 0


def test_snap_tracks_all_files(c, project):
    c.snap()
    manifest = json.loads((project / ".chuck" / "manifest.json").read_text())
    files = manifest["files"]
    assert "src/main.py" in files
    assert "src/utils.py" in files
    assert "README.md" in files


def test_snap_excludes_chuck_dir(c, project):
    c.snap()
    manifest = json.loads((project / ".chuck" / "manifest.json").read_text())
    for path in manifest["files"]:
        assert not path.startswith(".chuck/"), f".chuck/ file leaked: {path}"


def test_snap_quiet_returns_none(c, project):
    result = c.snap(quiet=True)
    assert result is None
    assert (project / ".chuck" / "manifest.json").exists()


def test_snap_output_markdown(c, project):
    result = c.snap(format="markdown")
    assert isinstance(result, str)
    assert "src/main.py" in result


def test_snap_output_xml(c, project):
    result = c.snap(format="xml")
    assert isinstance(result, str)
    assert "<chuck" in result


def test_snap_output_json_parseable(c, project):
    result = c.snap(format="json")
    assert isinstance(result, str)
    data = json.loads(result)
    assert "files" in data


def test_multiple_snaps_accumulate(c, project):
    c.snap()
    c.snap()
    snap_dir = project / ".chuck" / "snapshots"
    assert len(list(snap_dir.glob("*.json"))) == 2


# ─── patch ────────────────────────────────────────────────────────────────────

def test_patch_no_baseline_auto_snaps(c, project):
    result, auto_snapped = c.patch()
    assert auto_snapped is True
    assert (project / ".chuck" / "manifest.json").exists()


def test_patch_no_changes(c, project):
    c.snap()
    result, auto_snapped = c.patch()
    assert auto_snapped is False
    assert result is not None


def test_patch_with_changed_file(c, project):
    c.snap()
    (project / "src" / "main.py").write_text("def main():\n    print('changed')\n")
    result, auto_snapped = c.patch()
    assert auto_snapped is False
    assert "main.py" in result


def test_patch_does_not_advance_baseline(c, project):
    c.snap()
    ts_before = json.loads((project / ".chuck" / "manifest.json").read_text())["timestamp"]

    (project / "src" / "main.py").write_text("changed content\n")
    c.patch()

    ts_after = json.loads((project / ".chuck" / "manifest.json").read_text())["timestamp"]
    assert ts_before == ts_after, "patch() should not update the manifest"


def test_patch_writes_patch_md(c, project):
    c.snap()
    (project / "src" / "main.py").write_text("changed\n")
    c.patch()
    assert (project / ".chuck" / "patch.md").exists()


def test_patch_quiet_writes_patch_md(c, project):
    c.snap()
    result, _ = c.patch(quiet=True)
    assert result is None
    assert (project / ".chuck" / "patch.md").exists()


def test_patch_auto_snap_threshold_files(project):
    c = chuck.init(str(project))
    # Threshold: 1 file change triggers auto-snap
    c._config["settings"]["auto_snap_threshold"] = {"files": 1, "tokens": 999999}
    c.snap()
    (project / "src" / "main.py").write_text("changed content here\n")
    result, auto_snapped = c.patch()
    assert auto_snapped is True
    # Baseline should now be updated
    manifest = json.loads((project / ".chuck" / "manifest.json").read_text())
    assert manifest["files"]["src/main.py"] is not None


def test_patch_auto_snap_threshold_tokens(project):
    c = chuck.init(str(project))
    # Threshold: 1 token change triggers auto-snap
    c._config["settings"]["auto_snap_threshold"] = {"files": 999, "tokens": 1}
    c.snap()
    (project / "src" / "main.py").write_text("completely different content\n" * 10)
    result, auto_snapped = c.patch()
    assert auto_snapped is True


def test_patch_updates_state(c, project):
    c.snap()
    (project / "src" / "main.py").write_text("changed\n")
    c.patch()
    state = json.loads((project / ".chuck" / "state.json").read_text())
    assert state["changes_since_snap"]["files"] == 1


# ─── diff ─────────────────────────────────────────────────────────────────────

def test_diff_no_snapshot_raises(c, project):
    with pytest.raises(NoSnapshotError):
        c.diff()


def test_diff_no_changes(c, project):
    c.snap()
    diff = c.diff()
    assert not diff.has_changes


def test_diff_modified_file(c, project):
    c.snap()
    (project / "src" / "main.py").write_text("changed\n")
    diff = c.diff()
    assert diff.has_changes
    assert any(f.path == "src/main.py" for f in diff.modified)


def test_diff_added_file(c, project):
    c.snap()
    (project / "src" / "new.py").write_text("x = 1\n")
    diff = c.diff()
    assert diff.has_changes
    assert any(f.path == "src/new.py" for f in diff.added)


def test_diff_removed_file(c, project):
    c.snap()
    (project / "src" / "utils.py").unlink()
    diff = c.diff()
    assert diff.has_changes
    assert any(f.path == "src/utils.py" for f in diff.removed)


# ─── status ───────────────────────────────────────────────────────────────────

def test_status_no_snapshot(c, project):
    status = c.status()
    assert status["last_snapshot"] is None
    assert status["file_count"] == 0
    assert status["snapshot_count"] == 0


def test_status_after_snap(c, project):
    c.snap()
    status = c.status()
    assert status["last_snapshot"] is not None
    assert status["file_count"] > 0
    assert status["total_tokens"] > 0
    assert status["snapshot_count"] == 1


def test_status_root_is_string(c, project):
    status = c.status()
    assert isinstance(status["root"], str)
    assert str(project) in status["root"]


# ─── reset ────────────────────────────────────────────────────────────────────

def test_reset_clears_snapshots(c, project):
    c.snap()
    c.snap()
    c.reset()
    snap_dir = project / ".chuck" / "snapshots"
    assert len(list(snap_dir.glob("*.json"))) == 0


def test_reset_removes_manifest(c, project):
    c.snap()
    c.reset()
    assert not (project / ".chuck" / "manifest.json").exists()


def test_reset_removes_state(c, project):
    c.snap()
    c.reset()
    assert not (project / ".chuck" / "state.json").exists()


def test_reset_keeps_config(c, project):
    c.snap()
    c.reset()
    assert (project / ".chuck" / "config.json").exists()


# ─── ls ───────────────────────────────────────────────────────────────────────

def test_ls_finds_instances(tmp_path):
    root1 = tmp_path / "proj1"
    root1.mkdir()
    chuck.init(str(root1))

    root2 = tmp_path / "proj2"
    root2.mkdir()
    chuck.init(str(root2))

    instances = Chuck.ls(str(tmp_path))
    assert root1 in instances
    assert root2 in instances


def test_ls_empty_when_none(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    instances = Chuck.ls(str(empty))
    assert instances == []


# ─── integrate ────────────────────────────────────────────────────────────────

def test_integrate_claude(c, project):
    written = c.integrate("claude")
    assert "claude_md" in written
    claude_md = Path(written["claude_md"])
    assert claude_md.exists()
    assert "Chuck Context" in claude_md.read_text()


def test_integrate_agents(c, project):
    written = c.integrate("agents")
    assert "agents_md" in written
    agents_md = Path(written["agents_md"])
    assert agents_md.exists()
    assert "Chuck Context" in agents_md.read_text()


def test_integrate_goose(c, project):
    written = c.integrate("goose")
    assert "goose_context" in written
    goose_md = Path(written["goose_context"])
    assert goose_md.exists()
    assert "Chuck Context" in goose_md.read_text()


def test_integrate_kilo(c, project):
    written = c.integrate("kilo")
    assert "kilo_rules" in written
    kilo_rules = Path(written["kilo_rules"])
    assert kilo_rules.exists()
    assert kilo_rules == project / ".kilocode" / "rules" / "chuck.md"
    assert "Chuck Context" in kilo_rules.read_text()


def test_integrate_unknown_raises(c, project):
    with pytest.raises(ChuckError):
        c.integrate("unknown-agent")


def test_integrate_claude_appends_to_existing(c, project):
    claude_md = project / "CLAUDE.md"
    claude_md.write_text("# Existing content\n\nSome instructions here.\n")
    c.integrate("claude")
    content = claude_md.read_text()
    assert "# Existing content" in content
    assert "Chuck Context" in content


def test_integrate_claude_idempotent(c, project):
    c.integrate("claude")
    c.integrate("claude")  # second call should not duplicate
    content = (project / "CLAUDE.md").read_text()
    assert content.count("## Chuck Context") == 1


# ─── chuckignore ──────────────────────────────────────────────────────────────

def test_chuckignore_respected(project):
    (project / ".chuckignore").write_text("*.md\n")
    c = chuck.init(str(project))
    c.snap()
    manifest = json.loads((project / ".chuck" / "manifest.json").read_text())
    assert "README.md" not in manifest["files"]


def test_chuckignore_excludes_directory(project):
    (project / ".chuckignore").write_text("src/\n")
    c = chuck.init(str(project))
    c.snap()
    manifest = json.loads((project / ".chuck" / "manifest.json").read_text())
    for path in manifest["files"]:
        assert not path.startswith("src/"), f"src/ should be ignored but got: {path}"


# ─── misc ─────────────────────────────────────────────────────────────────────

def test_chuck_version():
    assert chuck.__version__ == "1.0.0"


def test_config_persists_across_instances(project):
    c1 = chuck.init(str(project))
    # Modify threshold
    c1._config["settings"]["auto_snap_threshold"]["files"] = 5
    c1._save_config()

    c2 = Chuck(project)
    assert c2._config["settings"]["auto_snap_threshold"]["files"] == 5
