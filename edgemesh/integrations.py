"""Generate ready-to-use VSCode + MCP integration configs for edgemesh.

`edgemesh vscode` prints these; `edgemesh vscode --write` drops them into the
current project so the editor's AI tooling immediately uses the local cluster:

  * `.vscode/mcp.json`  — VSCode / GitHub Copilot *agent mode* MCP server entry
  * `.mcp.json`         — Cline / Cursor / Claude Code MCP server entry
  * `.continue/config.json` — Continue: edgemesh as an OpenAI-compatible provider

All point at the edgemesh MCP server (`edgemesh mcp`) and/or the gateway's
OpenAI-compatible `/v1`, so the editor gets edgemesh's models *and* toolbelt.
"""

from __future__ import annotations

import json
from pathlib import Path

GATEWAY = "http://127.0.0.1:8780"


def _mcp_entry(root: str) -> dict:
    return {"command": "edgemesh", "args": ["mcp", "--root", root, "--gateway", GATEWAY]}


def vscode_configs(model: str = "") -> dict[str, str]:
    """Return {filename: json-text} for each integration config."""
    model = model or "<your-model-id>"
    vscode_mcp = {"servers": {"edgemesh": _mcp_entry("${workspaceFolder}")}}
    project_mcp = {"mcpServers": {"edgemesh": _mcp_entry(".")}}
    continue_cfg = {
        "models": [{
            "title": "edgemesh (local cluster)",
            "provider": "openai",
            "model": model,
            "apiBase": f"{GATEWAY}/v1",
            "apiKey": "edgemesh",
        }],
        "tabAutocompleteModel": {
            "title": "edgemesh autocomplete", "provider": "openai", "model": model,
            "apiBase": f"{GATEWAY}/v1", "apiKey": "edgemesh",
        },
    }
    cline_note = {
        "//": "Cline / Roo: set API Provider = OpenAI Compatible, Base URL below, any API key.",
        "openAiBaseUrl": f"{GATEWAY}/v1",
        "openAiModelId": model,
        "openAiApiKey": "edgemesh",
    }
    return {
        ".vscode/mcp.json": json.dumps(vscode_mcp, indent=2),
        ".mcp.json": json.dumps(project_mcp, indent=2),
        ".continue/config.json": json.dumps(continue_cfg, indent=2),
        "cline-settings.json": json.dumps(cline_note, indent=2),
    }


def write_vscode_configs(root: Path, model: str = "") -> list[str]:
    """Write the integration configs under ``root``; return the paths written."""
    written: list[str] = []
    for rel, blob in vscode_configs(model).items():
        if rel == "cline-settings.json":
            continue  # informational only — Cline stores settings in its own UI
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(blob + "\n", encoding="utf-8")
        written.append(str(path).replace("\\", "/"))
    return written


__all__ = ["vscode_configs", "write_vscode_configs"]
