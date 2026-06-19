"""A senior-developer toolbelt — the hands edgemesh uses to actually do software work.

Every capability a competent engineer reaches for, exposed as a small, safe,
*pure standard library* function: read/write/edit files, search the tree, run
tests and shell commands, and drive git. The same registry powers three callers:

  * the coding agent loop (``edgemesh.agent``) via OpenAI tool-calling,
  * the MCP server (``edgemesh.mcp_server``) for VSCode / Copilot / Cline / Claude,
  * the CLI (``edgemesh tools``) for humans.

Design rules:
  * **Sandboxed** — file operations resolve under a workspace root and refuse to
    escape it (no writing to ``/etc`` from a stray ``../../``).
  * **Bounded** — every shell/git call has a timeout; output is truncated so a
    runaway command can't blow up the context window.
  * **Honest** — failures come back as readable strings, never silent.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_OUTPUT = 20_000          # chars returned from any single tool call
DEFAULT_TIMEOUT = 120        # seconds for shell / test commands
GIT_TIMEOUT = 60


def _truncate(text: str, limit: int = MAX_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit - 200]
    return f"{head}\n... [truncated {len(text) - limit + 200} chars] ..."


class ToolError(Exception):
    """A tool failed in a way worth reporting back to the model verbatim."""


@dataclass
class Toolbelt:
    """Workspace-scoped developer tools. All paths are relative to ``root``."""

    root: Path

    def __init__(self, root: str | os.PathLike = ".") -> None:
        self.root = Path(root).resolve()
        if not self.root.exists():
            raise ToolError(f"workspace root does not exist: {self.root}")

    # ── path safety ──────────────────────────────────────────────────────────
    def _resolve(self, rel: str) -> Path:
        """Resolve ``rel`` under the workspace root, refusing to escape it."""
        p = (self.root / rel).resolve() if not os.path.isabs(rel) else Path(rel).resolve()
        try:
            p.relative_to(self.root)
        except ValueError:
            raise ToolError(f"path escapes the workspace root: {rel}")
        return p

    def _rel(self, p: Path) -> str:
        try:
            return str(p.relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return str(p)

    # ── files ────────────────────────────────────────────────────────────────
    def read_file(self, path: str, start: int = 1, end: int | None = None) -> str:
        """Read a text file (optionally a 1-based inclusive line range)."""
        p = self._resolve(path)
        if not p.is_file():
            raise ToolError(f"not a file: {path}")
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if end is None:
            end = len(lines)
        chosen = lines[max(start - 1, 0): end]
        width = len(str(end))
        body = "\n".join(f"{i:>{width}}  {ln}" for i, ln in enumerate(chosen, start=max(start, 1)))
        return _truncate(body) or "(empty file)"

    def write_file(self, path: str, content: str) -> str:
        """Create or overwrite a file (parent dirs auto-created)."""
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} chars to {self._rel(p)}"

    def edit_file(self, path: str, old: str, new: str, count: int = 1) -> str:
        """Replace an exact substring. ``count<=0`` replaces every occurrence."""
        p = self._resolve(path)
        if not p.is_file():
            raise ToolError(f"not a file: {path}")
        text = p.read_text(encoding="utf-8", errors="replace")
        found = text.count(old)
        if found == 0:
            raise ToolError("old string not found; read the file and match exactly (incl. whitespace)")
        if count > 0 and found > count:
            raise ToolError(f"old string is not unique ({found} matches); add more context or set count<=0")
        text = text.replace(old, new) if count <= 0 else text.replace(old, new, count)
        p.write_text(text, encoding="utf-8")
        return f"edited {self._rel(p)} ({found if count <= 0 else count} replacement(s))"

    def list_dir(self, path: str = ".") -> str:
        """List a directory (dirs first, trailing slash on dirs)."""
        p = self._resolve(path)
        if not p.is_dir():
            raise ToolError(f"not a directory: {path}")
        entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        return "\n".join((e.name + "/") if e.is_dir() else e.name for e in entries) or "(empty)"

    # ── search ───────────────────────────────────────────────────────────────
    def find_files(self, pattern: str = "*", path: str = ".") -> str:
        """Glob for files recursively (e.g. ``**/*.py`` or ``*.md``)."""
        base = self._resolve(path)
        pat = pattern if "**" in pattern or "/" in pattern else f"**/{pattern}"
        hits = [self._rel(p) for p in base.glob(pat) if p.is_file() and ".git" not in p.parts]
        return "\n".join(sorted(hits)[:500]) or "(no matches)"

    def grep(self, pattern: str, path: str = ".", glob: str = "*", flags: str = "") -> str:
        """Regex-search file contents. ``flags`` may contain 'i' (ignore case)."""
        base = self._resolve(path)
        rx = re.compile(pattern, re.IGNORECASE if "i" in flags else 0)
        targets = [base] if base.is_file() else [
            p for p in base.rglob("*")
            if p.is_file() and ".git" not in p.parts and fnmatch.fnmatch(p.name, glob)
        ]
        out: list[str] = []
        for fp in targets:
            try:
                for n, line in enumerate(fp.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if rx.search(line):
                        out.append(f"{self._rel(fp)}:{n}: {line.strip()[:200]}")
                        if len(out) >= 400:
                            return _truncate("\n".join(out)) + "\n... [400-match cap]"
            except OSError:
                continue
        return "\n".join(out) or "(no matches)"

    # ── execution ──────────────────────────────────────────────────────────────
    def run(self, command: str, timeout: int = DEFAULT_TIMEOUT) -> str:
        """Run a shell command in the workspace and capture stdout+stderr+exit code."""
        try:
            proc = subprocess.run(command, shell=True, cwd=self.root, capture_output=True,
                                  text=True, timeout=timeout, errors="replace")
        except subprocess.TimeoutExpired:
            raise ToolError(f"command timed out after {timeout}s: {command}")
        body = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
        return _truncate(f"$ {command}\n[exit {proc.returncode}]\n{body}".rstrip())

    def run_tests(self, target: str = "") -> str:
        """Auto-detect and run the project's test suite (pytest / npm test / go / cargo)."""
        if (self.root / "pyproject.toml").exists() or (self.root / "pytest.ini").exists() \
                or any(self.root.glob("tests")) or any(self.root.glob("test_*.py")):
            return self.run(f"python -m pytest -q {target}".strip(), timeout=600)
        if (self.root / "package.json").exists():
            return self.run(f"npm test {target}".strip(), timeout=600)
        if (self.root / "go.mod").exists():
            return self.run("go test ./...", timeout=600)
        if (self.root / "Cargo.toml").exists():
            return self.run("cargo test", timeout=600)
        raise ToolError("could not detect a test runner (no pyproject/package.json/go.mod/Cargo.toml)")

    # ── git ────────────────────────────────────────────────────────────────────
    def _git(self, *args: str, timeout: int = GIT_TIMEOUT) -> str:
        try:
            proc = subprocess.run(["git", "-C", str(self.root), *args],
                                  capture_output=True, text=True, timeout=timeout, errors="replace")
        except FileNotFoundError:
            raise ToolError("git is not installed or not on PATH")
        except subprocess.TimeoutExpired:
            raise ToolError(f"git timed out: git {' '.join(args)}")
        out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        if proc.returncode != 0 and not out.strip():
            out = f"[git exit {proc.returncode}]"
        return _truncate(out.rstrip()) or "(no output)"

    def git_status(self) -> str:
        return self._git("status", "--short", "--branch")

    def git_diff(self, target: str = "", staged: bool = False) -> str:
        args = ["diff"] + (["--staged"] if staged else []) + ([target] if target else [])
        return self._git(*args)

    def git_log(self, n: int = 15, target: str = "") -> str:
        args = ["log", f"-{n}", "--oneline", "--decorate"] + ([target] if target else [])
        return self._git(*args)

    def git_add(self, paths: str = ".") -> str:
        self._git("add", *shlex.split(paths))
        return self._git("status", "--short")

    def git_commit(self, message: str) -> str:
        return self._git("commit", "-m", message)

    def git_branch(self, name: str = "") -> str:
        return self._git("branch", "--show-current") if not name else self._git("checkout", "-b", name)

    def git_checkout(self, ref: str) -> str:
        return self._git("checkout", ref)

    def git_show(self, ref: str = "HEAD") -> str:
        return self._git("show", "--stat", ref)


# ── tool registry (OpenAI / MCP schemas + dispatch) ──────────────────────────
# Each entry: (method_name, description, json-schema-properties, required[]).
_SPECS: list[tuple[str, str, dict, list[str]]] = [
    ("read_file", "Read a text file, optionally a 1-based inclusive line range.",
     {"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}, ["path"]),
    ("write_file", "Create or overwrite a file with the given content.",
     {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    ("edit_file", "Replace an exact substring in a file. count<=0 replaces all occurrences.",
     {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"},
      "count": {"type": "integer"}}, ["path", "old", "new"]),
    ("list_dir", "List the entries of a directory.", {"path": {"type": "string"}}, []),
    ("find_files", "Glob for files recursively (e.g. **/*.py).",
     {"pattern": {"type": "string"}, "path": {"type": "string"}}, []),
    ("grep", "Regex-search file contents; flags may include 'i' for ignore-case.",
     {"pattern": {"type": "string"}, "path": {"type": "string"}, "glob": {"type": "string"},
      "flags": {"type": "string"}}, ["pattern"]),
    ("run", "Run a shell command in the workspace; returns stdout+stderr+exit code.",
     {"command": {"type": "string"}, "timeout": {"type": "integer"}}, ["command"]),
    ("run_tests", "Auto-detect and run the project's test suite.",
     {"target": {"type": "string"}}, []),
    ("git_status", "Show git working-tree status (short + branch).", {}, []),
    ("git_diff", "Show a git diff. Set staged=true for the index.",
     {"target": {"type": "string"}, "staged": {"type": "boolean"}}, []),
    ("git_log", "Show recent commits (oneline).",
     {"n": {"type": "integer"}, "target": {"type": "string"}}, []),
    ("git_add", "Stage paths (space-separated; default all).", {"paths": {"type": "string"}}, []),
    ("git_commit", "Commit staged changes with a message.", {"message": {"type": "string"}}, ["message"]),
    ("git_branch", "Show the current branch, or create+switch to one if 'name' given.",
     {"name": {"type": "string"}}, []),
    ("git_checkout", "Check out a branch, commit, or path.", {"ref": {"type": "string"}}, ["ref"]),
    ("git_show", "Show a commit (with file stats).", {"ref": {"type": "string"}}, []),
]


def openai_tools() -> list[dict]:
    """Return the toolbelt as OpenAI ``tools=[...]`` function specs."""
    return [{
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req},
        },
    } for name, desc, props, req in _SPECS]


def mcp_tools() -> list[dict]:
    """Return the toolbelt as MCP ``tools/list`` descriptors."""
    return [{
        "name": name,
        "description": desc,
        "inputSchema": {"type": "object", "properties": props, "required": req},
    } for name, desc, props, req in _SPECS]


TOOL_NAMES = [name for name, *_ in _SPECS]


def dispatch(belt: Toolbelt, name: str, arguments: dict | None) -> str:
    """Execute tool ``name`` with ``arguments`` against ``belt``; always returns a string."""
    if name not in TOOL_NAMES:
        return f"error: unknown tool {name!r}"
    fn = getattr(belt, name)
    try:
        return fn(**(arguments or {}))
    except ToolError as exc:
        return f"error: {exc}"
    except TypeError as exc:
        return f"error: bad arguments for {name}: {exc}"
    except Exception as exc:  # noqa: BLE001 - surface anything to the model
        return f"error: {name} failed: {exc}"


__all__ = ["Toolbelt", "ToolError", "openai_tools", "mcp_tools", "dispatch", "TOOL_NAMES"]
