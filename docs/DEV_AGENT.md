# Developer agent, toolbelt & VSCode / MCP integration

edgemesh isn't only a gateway — it's a place to *do* software work on your own
models. v0.13 adds a sandboxed developer toolbelt, a senior-engineer coding
agent, an MCP server, and a VSCode extension. Everything runs against whatever
your cluster fronts (Cognis fleet, Ollama, llama.cpp, vLLM, hosted).

## 1. The toolbelt

A pure-stdlib, workspace-sandboxed set of tools (`edgemesh.devtools.Toolbelt`):

| Group | Tools |
| --- | --- |
| Files | `read_file`, `write_file`, `edit_file`, `list_dir` |
| Search | `find_files`, `grep` |
| Execute | `run` (shell), `run_tests` (auto-detects pytest/npm/go/cargo) |
| Git | `git_status`, `git_diff`, `git_log`, `git_add`, `git_commit`, `git_branch`, `git_checkout`, `git_show` |

File paths are confined to the workspace root; shell/git calls are timed out and
output-truncated. List them with `edgemesh tools`.

## 2. The coding agent

```
edgemesh serve &                     # gateway with at least one backend
edgemesh agent "add a --json flag to the report command and update its test"
```

The agent runs a senior-engineer loop — investigate → make the smallest correct
change → run tests → use git deliberately — using the toolbelt via OpenAI
tool-calling. Flags: `--model`, `--gateway`, `--root`, `--max-steps`.

## 3. MCP server (VSCode, Copilot, Cline, Cursor, Continue, Claude)

```
edgemesh mcp --root .                 # stdio JSON-RPC; mount from any MCP client
```

Exposes the whole toolbelt plus `edgemesh_agent` and `edgemesh_chat`. Generate
client configs automatically:

```
edgemesh vscode --write               # writes .vscode/mcp.json, .mcp.json, .continue/config.json
```

- **GitHub Copilot agent mode** reads `.vscode/mcp.json`.
- **Cline / Cursor / Claude** read `.mcp.json` (`mcpServers`).
- **Continue** reads `.continue/config.json` (edgemesh as an OpenAI provider).

## 4. The VSCode extension

`edgemesh-vscode/` — chat sidebar, *Run Coding Agent on a Task*, AI commit
messages from the staged diff, *Explain Selection*, and one-click MCP setup.

```
cd edgemesh-vscode && npm install && npm run compile   # then press F5 to debug
```

Settings: `edgemesh.gateway` (default `http://127.0.0.1:8780`) and
`edgemesh.model` (empty = first model the gateway reports).
