"""Tests for snapshot creation and diffing."""

import json
import pytest
from pathlib import Path
from chuck.snapshot import build_snapshot, diff_snapshots, Snapshot, FileRecord


@pytest.fixture
def project(tmp_path):
    """Create a small test project."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("def main():\n    print('hello')\n")
    (src / "utils.py").write_text("def helper():\n    return 42\n")
    (tmp_path / "README.md").write_text("# Test Project\n")
    return tmp_path


def test_build_snapshot(project):
    files = list(project.rglob("*"))
    files = [f for f in files if f.is_file()]
    snap = build_snapshot("test", files, project)

    assert snap.context_name == "test"
    assert snap.file_count == len(files)
    assert snap.total_tokens > 0
    assert snap.timestamp


def test_snapshot_hashes_files(project):
    files = list((project / "src").rglob("*.py"))
    snap = build_snapshot("src", files, project)

    for rel_path, rec in snap.files.items():
        assert rec.hash, f"Expected hash for {rel_path}"
        assert rec.size > 0


def test_snapshot_serialization(project, tmp_path):
    files = list(project.rglob("*"))
    files = [f for f in files if f.is_file()]
    snap = build_snapshot("test", files, project)

    snap_path = tmp_path / "snap.json"
    snap.save(snap_path)
    loaded = Snapshot.load(snap_path, project)

    assert loaded.context_name == snap.context_name
    assert loaded.timestamp == snap.timestamp
    assert set(loaded.files.keys()) == set(snap.files.keys())
    for path, rec in snap.files.items():
        assert loaded.files[path].hash == rec.hash


def test_diff_added_file(project):
    files = [project / "src" / "main.py"]
    snap1 = build_snapshot("test", files, project)

    # Add a new file
    (project / "src" / "new.py").write_text("x = 1\n")
    files2 = [project / "src" / "main.py", project / "src" / "new.py"]
    snap2 = build_snapshot("test", files2, project)

    diff = diff_snapshots("test", snap1, snap2, project)

    assert diff.has_changes
    assert any(f.path == "src/new.py" for f in diff.added)
    assert not diff.removed
    assert not diff.modified


def test_diff_removed_file(project):
    files = [project / "src" / "main.py", project / "src" / "utils.py"]
    snap1 = build_snapshot("test", files, project)

    files2 = [project / "src" / "main.py"]
    snap2 = build_snapshot("test", files2, project)

    diff = diff_snapshots("test", snap1, snap2, project)

    assert diff.has_changes
    assert any(f.path == "src/utils.py" for f in diff.removed)
    assert not diff.added
    assert not diff.modified


def test_diff_modified_file(project):
    files = [project / "src" / "main.py"]
    snap1 = build_snapshot("test", files, project)

    # Modify the file
    (project / "src" / "main.py").write_text("def main():\n    print('changed')\n")
    snap2 = build_snapshot("test", files, project)

    diff = diff_snapshots("test", snap1, snap2, project)

    assert diff.has_changes
    assert any(f.path == "src/main.py" for f in diff.modified)
    assert not diff.added
    assert not diff.removed


def test_diff_no_changes(project):
    files = [project / "src" / "main.py"]
    snap1 = build_snapshot("test", files, project)
    snap2 = build_snapshot("test", files, project)

    diff = diff_snapshots("test", snap1, snap2, project)
    assert not diff.has_changes


def test_diff_modified_has_hash_change(project):
    """Verify modified files show old and new hashes (Chuck is metadata-only)."""
    files = [project / "src" / "main.py"]
    snap1 = build_snapshot("test", files, project)
    old_hash = snap1.files["src/main.py"].hash

    (project / "src" / "main.py").write_text("def main():\n    print('new')\n")
    snap2 = build_snapshot("test", files, project)

    diff = diff_snapshots("test", snap1, snap2, project)
    assert diff.modified[0].old_hash == old_hash
    assert diff.modified[0].new_hash != old_hash


def test_diff_from_none(project):
    """Diffing with no previous snapshot treats everything as added."""
    files = [project / "src" / "main.py"]
    snap2 = build_snapshot("test", files, project)
    diff = diff_snapshots("test", None, snap2, project)

    assert diff.has_changes
    assert diff.added
    assert not diff.removed
    assert not diff.modified


def test_token_cache_used(project):
    """Token cache avoids re-counting unchanged files."""
    cache = {}
    files = [project / "src" / "main.py"]
    snap1 = build_snapshot("test", files, project, token_cache=cache)
    assert len(cache) == 1

    # Build again — cache should be reused (same hash)
    snap2 = build_snapshot("test", files, project, token_cache=cache)
    assert snap1.files["src/main.py"].tokens == snap2.files["src/main.py"].tokens
