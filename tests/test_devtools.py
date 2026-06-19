"""Developer toolbelt: file ops, search, sandboxing, shell, and git."""

from __future__ import annotations

import subprocess

import pytest

from edgemesh.devtools import (Toolbelt, ToolError, dispatch, mcp_tools,
                               openai_tools, TOOL_NAMES)


@pytest.fixture()
def belt(tmp_path):
    (tmp_path / "a.txt").write_text("hello\nworld\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("def foo():\n    return 42\n", encoding="utf-8")
    return Toolbelt(tmp_path)


def test_read_write_edit(belt):
    assert "hello" in belt.read_file("a.txt")
    assert "world" in belt.read_file("a.txt", start=2, end=2)
    belt.write_file("new/deep.txt", "X")
    assert belt.read_file("new/deep.txt").strip().endswith("X")
    belt.edit_file("a.txt", "world", "earth")
    assert "earth" in belt.read_file("a.txt")


def test_edit_requires_unique_match(belt):
    belt.write_file("dup.txt", "x x x")
    with pytest.raises(ToolError):
        belt.edit_file("dup.txt", "x", "y")          # ambiguous
    assert "y y y" in (belt.edit_file("dup.txt", "x", "y", count=0), belt.read_file("dup.txt"))[1]


def test_missing_edit_target(belt):
    with pytest.raises(ToolError):
        belt.edit_file("a.txt", "nope-not-here", "z")


def test_find_and_grep(belt):
    assert "pkg/m.py" in belt.find_files("**/*.py")
    hits = belt.grep("def foo", glob="*.py")
    assert "m.py" in hits and ":1:" in hits
    assert belt.grep("ZZZnope") == "(no matches)"


def test_list_dir(belt):
    out = belt.list_dir(".")
    assert "pkg/" in out and "a.txt" in out


def test_sandbox_escape(belt):
    with pytest.raises(ToolError):
        belt.read_file("../../etc/passwd")
    with pytest.raises(ToolError):
        belt.write_file("../escape.txt", "no")


def test_run_captures_exit(belt):
    out = belt.run("python -c \"print('ok')\"")
    assert "ok" in out and "[exit 0]" in out


def test_run_tests_detects_nothing(belt):
    # bare tmp dir has no recognizable test runner
    with pytest.raises(ToolError):
        belt.run_tests()


def test_git_flow(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    belt = Toolbelt(tmp_path)
    belt.write_file("f.txt", "v1")
    assert "f.txt" in belt.git_status()
    belt.git_add("f.txt")
    assert "f.txt" in belt.git_commit("init: add f")
    assert "init: add f" in belt.git_log()
    belt.git_branch("feature")
    assert "feature" in belt.git_branch()


def test_dispatch_and_schemas(belt):
    assert dispatch(belt, "read_file", {"path": "a.txt"}).startswith("1")
    assert dispatch(belt, "nope", {}).startswith("error: unknown tool")
    assert dispatch(belt, "read_file", {"path": "missing.txt"}).startswith("error:")
    names = {t["function"]["name"] for t in openai_tools()}
    assert names == set(TOOL_NAMES)
    assert {t["name"] for t in mcp_tools()} == set(TOOL_NAMES)
