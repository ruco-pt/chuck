"""Tests for .chuckignore pattern matching."""

import pytest
from pathlib import Path
from chuck.ignore import IgnoreFilter, DEFAULT_PATTERNS


def make_filter(*patterns) -> IgnoreFilter:
    # Override defaults so we only test what we pass
    f = IgnoreFilter.__new__(IgnoreFilter)
    f.root = Path("/project")
    f._rules = []
    for p in patterns:
        f._add_pattern(p)
    return f


def test_defaults_ignore_git():
    f = IgnoreFilter(root=Path("/project"))
    assert f.is_ignored(Path("/project/.git/config"))


def test_defaults_ignore_pycache():
    f = IgnoreFilter(root=Path("/project"))
    assert f.is_ignored(Path("/project/__pycache__/foo.pyc"))


def test_defaults_ignore_pyc():
    f = IgnoreFilter(root=Path("/project"))
    assert f.is_ignored(Path("/project/src/foo.pyc"))


def test_wildcard_extension():
    f = make_filter("*.log")
    assert f.is_ignored(Path("/project/app.log"))
    assert not f.is_ignored(Path("/project/app.py"))


def test_directory_pattern():
    f = make_filter("dist/")
    assert f.is_ignored(Path("/project/dist/bundle.js"))


def test_double_star_glob():
    f = make_filter("**/*.test.js")
    assert f.is_ignored(Path("/project/src/foo.test.js"))
    assert f.is_ignored(Path("/project/src/sub/foo.test.js"))
    assert not f.is_ignored(Path("/project/src/foo.js"))


def test_comments_ignored():
    f = make_filter("# this is a comment", "*.pyc")
    assert f.is_ignored(Path("/project/foo.pyc"))


def test_blank_lines_ignored():
    f = make_filter("", "   ", "*.pyc")
    assert f.is_ignored(Path("/project/foo.pyc"))


def test_filter_list():
    f = IgnoreFilter(root=Path("/project"))
    paths = [
        Path("/project/src/main.py"),
        Path("/project/__pycache__/main.cpython-311.pyc"),
        Path("/project/app.pyc"),
    ]
    result = f.filter(paths)
    assert Path("/project/src/main.py") in result
    assert Path("/project/__pycache__/main.cpython-311.pyc") not in result
    assert Path("/project/app.pyc") not in result


def test_from_file(tmp_path):
    ignore_file = tmp_path / ".chuckignore"
    ignore_file.write_text("*.log\nbuild/\n")
    f = IgnoreFilter.from_file(ignore_file, root=tmp_path)
    assert f.is_ignored(tmp_path / "server.log")
    assert f.is_ignored(tmp_path / "build" / "output.js")
    assert not f.is_ignored(tmp_path / "src" / "main.py")
