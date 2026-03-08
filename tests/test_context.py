"""Tests for context definition and file resolution."""

import pytest
from pathlib import Path
from chuck.context import ContextDef


@pytest.fixture
def project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("# main")
    (src / "utils.py").write_text("# utils")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text("# test")
    (tmp_path / "README.md").write_text("# readme")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "output.js").write_text("// build artifact")
    return tmp_path


def test_resolve_glob_pattern(project):
    ctx = ContextDef(name="src", paths=["src/**/*.py"])
    files = ctx.resolve_files(project)
    rel_paths = {f.relative_to(project).as_posix() for f in files}
    assert "src/main.py" in rel_paths
    assert "src/utils.py" in rel_paths
    assert "tests/test_main.py" not in rel_paths


def test_resolve_multiple_patterns(project):
    ctx = ContextDef(name="all_py", paths=["src/**/*.py", "tests/**/*.py"])
    files = ctx.resolve_files(project)
    rel_paths = {f.relative_to(project).as_posix() for f in files}
    assert "src/main.py" in rel_paths
    assert "tests/test_main.py" in rel_paths
    assert "README.md" not in rel_paths


def test_resolve_directory_pattern(project):
    ctx = ContextDef(name="src", paths=["src/"])
    files = ctx.resolve_files(project)
    rel_paths = {f.relative_to(project).as_posix() for f in files}
    assert "src/main.py" in rel_paths
    assert "src/utils.py" in rel_paths


def test_resolve_ignores_extra_patterns(project):
    ctx = ContextDef(name="src", paths=["src/**/*.py"], ignore=["**/utils.py"])
    files = ctx.resolve_files(project)
    rel_paths = {f.relative_to(project).as_posix() for f in files}
    assert "src/main.py" in rel_paths
    assert "src/utils.py" not in rel_paths


def test_resolve_respects_chuckignore(project):
    chuckignore = project / ".chuckignore"
    chuckignore.write_text("build/\n")
    ctx = ContextDef(name="all", paths=["**/*.js", "**/*.py"])
    files = ctx.resolve_files(project, chuckignore)
    rel_paths = {f.relative_to(project).as_posix() for f in files}
    assert "build/output.js" not in rel_paths


def test_serialization():
    ctx = ContextDef(name="src", paths=["src/**/*.py"], ignore=["*.pyc"])
    d = ctx.to_dict()
    ctx2 = ContextDef.from_dict(d)
    assert ctx2.name == ctx.name
    assert ctx2.paths == ctx.paths
    assert ctx2.ignore == ctx.ignore


def test_no_duplicate_files(project):
    ctx = ContextDef(name="src", paths=["src/**/*.py", "src/main.py"])
    files = ctx.resolve_files(project)
    paths = [f.as_posix() for f in files]
    assert len(paths) == len(set(paths)), "Duplicate files returned"
