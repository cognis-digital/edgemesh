# edgemesh for VSCode

Code with your own [edgemesh](https://github.com/cognis-digital/edgemesh) cluster — local and self-hosted models, no cloud key required. The extension talks to the edgemesh gateway's OpenAI-compatible `/v1`, and wires the editor into edgemesh's senior-engineer agent and developer toolbelt.

## Features

- **Chat sidebar** — streaming chat with whatever model your cluster fronts (Cognis fleet, Ollama, llama.cpp, vLLM, hosted).
- **Coding agent** — *edgemesh: Run Coding Agent on a Task* hands a task to the autonomous senior-engineer agent, which reads/edits files, runs tests, and uses git in your workspace.
- **AI commit messages** — the sparkle button in Source Control writes a Conventional Commits message from your staged diff.
- **Explain selection** — right-click any code → *edgemesh: Explain Selection*.
- **One-click MCP setup** — *edgemesh: Set Up MCP + VSCode Configs* drops `.vscode/mcp.json`, `.mcp.json`, and `.continue/config.json` so GitHub Copilot agent mode, Cline, Cursor, Continue, and Claude all gain edgemesh's tools + models.

## Requirements

1. Install edgemesh and start the gateway:
   ```
   pip install edgemesh        # or: pipx install edgemesh
   edgemesh fleet --save       # register local backends
   edgemesh serve              # gateway on http://127.0.0.1:8780
   ```
2. (Agent command) the `edgemesh` CLI must be on your PATH.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `edgemesh.gateway` | `http://127.0.0.1:8780` | Gateway base URL (`/v1` lives here). |
| `edgemesh.model` | _(empty)_ | Model id; empty uses the first the gateway reports. |

## Build from source

```
cd edgemesh-vscode
npm install
npm run compile      # outputs ./out
```
Press **F5** in VSCode to launch an Extension Development Host.
