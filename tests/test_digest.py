"""Tests for digest generation and formatting."""

import json
import pytest
from pathlib import Path
from chuck.snapshot import build_snapshot
from chuck.digest import build_digest, build_diff_digest
from chuck.snapshot import diff_snapshots


@pytest.fixture
def project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("def main():\n    print('hello')\n")
    (src / "utils.py").write_text("def helper():\n    return 42\n")
    return tmp_path


@pytest.fixture
def snap(project):
    files = list((project / "src").rglob("*.py"))
    return build_snapshot("src", files, project)


def test_digest_markdown_default(project, snap):
    result = build_digest("src", snap, root=project)
    assert isinstance(result, str)
    assert "# Context: src" in result
    assert "src/main.py" in result
    assert "src/utils.py" in result
    assert "```python" in result


def test_digest_xml(project, snap):
    result = build_digest("src", snap, root=project, format="xml")
    assert isinstance(result, str)
    assert '<chuck context="src"' in result
    assert '<file path="src/main.py"' in result or '<file path="src/utils.py"' in result
    assert "<content><![CDATA[" in result


def test_digest_json(project, snap):
    result = build_digest("src", snap, root=project, format="json")
    assert isinstance(result, str)
    data = json.loads(result)
    assert data["context"] == "src"
    assert isinstance(data["files"], list)
    assert len(data["files"]) == 2
    assert "content" in data["files"][0]


def test_digest_with_budget_returns_list(project, snap):
    # Use tiny budget to force chunking
    result = build_digest("src", snap, root=project, token_budget=5)
    assert isinstance(result, list)
    assert len(result) >= 2
    for chunk_str in result:
        assert "src" in chunk_str


def test_digest_token_metadata(project, snap):
    result = build_digest("src", snap, root=project, format="markdown")
    assert "Tokens:" in result
    assert "Files:" in result


def test_diff_digest_markdown(project, snap):
    # Modify a file and create new snapshot
    (project / "src" / "main.py").write_text("def main():\n    print('changed')\n")
    files = list((project / "src").rglob("*.py"))
    snap2 = build_snapshot("src", files, project)
    diff = diff_snapshots("src", snap, snap2, project)

    result = build_diff_digest("src", diff, snap2, root=project)
    assert isinstance(result, str)
    assert "Diff Digest" in result
    assert "modified" in result.lower() or "src/main.py" in result


def test_diff_digest_no_changes(project, snap):
    # No-change diff
    files = list((project / "src").rglob("*.py"))
    snap2 = build_snapshot("src", files, project)
    diff = diff_snapshots("src", snap, snap2, project)

    result = build_diff_digest("src", diff, snap2, root=project)
    assert isinstance(result, str)
    assert "No changes" in result or "_No changes._" in result


def test_digest_custom_token_counter(project, snap):
    counter = lambda text: 999
    result = build_digest("src", snap, root=project, token_counter=counter)
    assert isinstance(result, (str, list))


def test_digest_json_format_chunk(project, snap):
    result = build_digest("src", snap, root=project, token_budget=5, format="json")
    assert isinstance(result, list)
    for chunk_str in result:
        data = json.loads(chunk_str)
        assert "context" in data
        assert "files" in data
