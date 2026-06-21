"""Model acquisition: download/install/list/remove models on this node.

edgemesh itself serves nothing — it meshes backends. But "download any model and
fit it to the cluster" means edgemesh needs to *drive* whatever backend tooling
is installed. This module shells out to the right tool for a catalog entry:

  - "ollama:<tag>"  -> `ollama pull <tag>`            (and `ollama list` / `ollama rm`)
  - "hf:<repo>"     -> `huggingface-cli download <repo>` (or the newer `hf download`)

Every operation degrades gracefully: if the tool isn't installed we return a
clear, actionable message (how to get it) instead of crashing.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from edgemesh.catalog import ModelCard


@dataclass
class ToolStatus:
    name: str
    present: bool
    hint: str = ""


def tools() -> list[ToolStatus]:
    """Which model-acquisition tools are available on this node."""
    hf = shutil.which("huggingface-cli") or shutil.which("hf")
    return [
        ToolStatus("ollama", bool(shutil.which("ollama")),
                   "install from https://ollama.com/download"),
        ToolStatus("huggingface-cli", bool(hf),
                   "pip install -U 'huggingface_hub[cli]'"),
    ]


def _has(tool: str) -> bool:
    return any(t.present for t in tools() if t.name == tool)


def _hf_cmd() -> list[str] | None:
    if shutil.which("hf"):
        return ["hf", "download"]
    if shutil.which("huggingface-cli"):
        return ["huggingface-cli", "download"]
    return None


def pull(card: ModelCard, *, dry_run: bool = False) -> tuple[bool, str]:
    """Acquire a catalog model with the appropriate tool. Returns (ok, message)."""
    kind, _, ref = card.pull.partition(":")
    if kind == "ollama":
        cmd = ["ollama", "pull", ref]
        tool_ok = _has("ollama")
        missing = "ollama is not installed — install from https://ollama.com/download"
    elif kind == "hf":
        hf = _hf_cmd()
        cmd = (hf or ["huggingface-cli", "download"]) + [ref]
        tool_ok = hf is not None
        missing = "Hugging Face CLI not installed — run: pip install -U 'huggingface_hub[cli]'"
    else:
        return False, f"unknown pull scheme {kind!r} for {card.id}"

    # A dry run only *builds* the command — it must not require the tool to be
    # installed, or it can't run in CI / on a fresh box (this was the CI failure).
    if dry_run:
        return True, "DRY RUN: " + " ".join(cmd)
    if not tool_ok:
        return False, missing
    try:
        p = subprocess.run(cmd)  # stream to the user's terminal
        ok = p.returncode == 0
        return ok, ("pulled " + card.id) if ok else f"{cmd[0]} exited {p.returncode}"
    except Exception as exc:  # pragma: no cover - environment dependent
        return False, f"failed to run {cmd[0]}: {exc}"


def local_ollama_models() -> list[str]:
    """Tags of models already pulled into a local Ollama, or [] if none/absent."""
    if not _has("ollama"):
        return []
    try:
        p = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
    except Exception:  # pragma: no cover
        return []
    if p.returncode != 0:
        return []
    names = []
    for line in p.stdout.splitlines()[1:]:  # skip header
        tag = line.split()[0] if line.split() else ""
        if tag:
            names.append(tag)
    return names


def remove(card_or_tag: ModelCard | str) -> tuple[bool, str]:
    """Remove a locally-pulled Ollama model (HF removal is just file deletion)."""
    if isinstance(card_or_tag, ModelCard):
        kind, _, ref = card_or_tag.pull.partition(":")
        if kind != "ollama":
            return False, "only Ollama models can be removed via edgemesh; delete HF caches manually"
        tag = ref
    else:
        tag = card_or_tag
    if not _has("ollama"):
        return False, "ollama is not installed"
    try:
        p = subprocess.run(["ollama", "rm", tag], capture_output=True, text=True)
        return p.returncode == 0, (p.stdout or p.stderr).strip() or f"removed {tag}"
    except Exception as exc:  # pragma: no cover
        return False, str(exc)
