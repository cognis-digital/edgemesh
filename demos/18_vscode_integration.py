"""Scenario 18 - editor integration: wire edgemesh into VSCode / MCP clients.

`edgemesh vscode` emits ready-to-use configs so an editor's AI tooling uses your
local cluster: a VSCode/Copilot agent-mode MCP entry, an .mcp.json for
Cline/Cursor/Claude Code, and a Continue provider pointed at the gateway's /v1.
This demo generates them (writing to a temp dir) and prints one. Offline.
"""
import json
import tempfile
from pathlib import Path

from _common import rule

from edgemesh import integrations


def main() -> None:
    rule("EDITOR INTEGRATION  -  edgemesh in VSCode / Copilot / Cline / Continue")

    cfgs = integrations.vscode_configs(model="qwen2.5-coder-7b")
    print("\nGenerated integration configs:")
    for name in cfgs:
        print(f"   {name}")

    print("\n.continue/config.json (Continue as an OpenAI-compatible provider):")
    cont = json.loads(cfgs[".continue/config.json"])
    m = cont["models"][0]
    print(f"   title   : {m['title']}")
    print(f"   provider: {m['provider']}")
    print(f"   model   : {m['model']}")
    print(f"   apiBase : {m['apiBase']}  (the edgemesh gateway)")

    out_dir = Path(tempfile.mkdtemp(prefix="edgemesh_demo_"))
    written = integrations.write_vscode_configs(out_dir, model="qwen2.5-coder-7b")
    print(f"\nWrote {len(written)} config files under {out_dir}:")
    for p in written:
        print(f"   {p}")
    print("   (the informational Cline note is intentionally NOT written to disk)")

    print("\nDrop these in a project and the editor's agent gets edgemesh's models")
    print("AND its developer toolbelt (files, search, shell, tests, git) via MCP.")


if __name__ == "__main__":
    main()
