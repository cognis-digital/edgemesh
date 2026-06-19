// edgemesh VSCode extension: chat sidebar, autonomous coding agent, AI commit
// messages, explain-selection, and one-click MCP/VSCode config setup — all
// powered by the local edgemesh cluster behind the OpenAI-compatible gateway.
import * as vscode from "vscode";
import { chat, chatStream, resolveModel, gateway, Msg } from "./api";

function workspaceRoot(): string {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || ".";
}

// Run an `edgemesh` CLI subcommand in a dedicated terminal so the user watches
// the agent operate on their real workspace.
function runInTerminal(name: string, args: string[]) {
  const term = vscode.window.terminals.find((t) => t.name === name)
    || vscode.window.createTerminal({ name, cwd: workspaceRoot() });
  term.show();
  term.sendText(`edgemesh ${args.join(" ")}`);
}

export function activate(context: vscode.ExtensionContext) {
  const provider = new ChatViewProvider(context);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("edgemesh.chat", provider),

    vscode.commands.registerCommand("edgemesh.focusChat", () =>
      vscode.commands.executeCommand("edgemesh.chat.focus")),

    vscode.commands.registerCommand("edgemesh.runAgent", async () => {
      const task = await vscode.window.showInputBox({
        prompt: "Task for the edgemesh coding agent",
        placeHolder: "e.g. add input validation to the login handler and run the tests",
      });
      if (!task) return;
      const g = gateway();
      runInTerminal("edgemesh agent", [
        "agent", JSON.stringify(task), "--gateway", g, "--root", JSON.stringify(workspaceRoot()),
      ]);
    }),

    vscode.commands.registerCommand("edgemesh.setupMcp", () => {
      runInTerminal("edgemesh setup", ["vscode", "--write"]);
      vscode.window.showInformationMessage(
        "edgemesh: wrote .vscode/mcp.json, .mcp.json and .continue/config.json. Reload to let Copilot/Cline/Continue pick them up.");
    }),

    vscode.commands.registerCommand("edgemesh.explainSelection", async () => {
      const ed = vscode.window.activeTextEditor;
      if (!ed || ed.selection.isEmpty) {
        vscode.window.showWarningMessage("Select some code first.");
        return;
      }
      const code = ed.document.getText(ed.selection);
      await withProgress("edgemesh: explaining…", async () => {
        const out = await chat([
          { role: "system", content: "You are a senior engineer. Explain the code clearly and concisely, noting bugs or risks." },
          { role: "user", content: "```\n" + code + "\n```" },
        ]);
        const doc = await vscode.workspace.openTextDocument({ content: out, language: "markdown" });
        vscode.window.showTextDocument(doc, { viewColumn: vscode.ViewColumn.Beside });
      });
    }),

    vscode.commands.registerCommand("edgemesh.commitWithAI", async () => {
      await withProgress("edgemesh: writing commit message…", async () => {
        const diff = await gitStagedDiff();
        if (!diff.trim()) {
          vscode.window.showWarningMessage("Nothing staged. Stage changes first.");
          return;
        }
        const msg = await chat([
          { role: "system", content: "Write a single concise Conventional Commits message (type(scope): subject, optional body) for this staged diff. Output only the message." },
          { role: "user", content: diff.slice(0, 12000) },
        ]);
        const git = vscode.extensions.getExtension("vscode.git")?.exports?.getAPI(1);
        const repo = git?.repositories?.[0];
        if (repo) {
          repo.inputBox.value = msg.trim();
          vscode.window.showInformationMessage("edgemesh: commit message ready in the Source Control box.");
        } else {
          const doc = await vscode.workspace.openTextDocument({ content: msg, language: "git-commit" });
          vscode.window.showTextDocument(doc);
        }
      });
    }),
  );
}

async function withProgress<T>(title: string, fn: () => Promise<T>): Promise<T | undefined> {
  try {
    return await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title }, fn);
  } catch (e: any) {
    vscode.window.showErrorMessage(`edgemesh: ${e.message || e}`);
    return undefined;
  }
}

async function gitStagedDiff(): Promise<string> {
  const cp = await import("child_process");
  return new Promise((resolve) => {
    cp.execFile("git", ["-C", workspaceRoot(), "diff", "--staged"],
      { maxBuffer: 10 * 1024 * 1024 }, (_e, stdout) => resolve(stdout || ""));
  });
}

class ChatViewProvider implements vscode.WebviewViewProvider {
  constructor(private readonly ctx: vscode.ExtensionContext) {}

  resolveWebviewView(view: vscode.WebviewView) {
    view.webview.options = { enableScripts: true };
    view.webview.html = this.html();
    const history: Msg[] = [
      { role: "system", content: "You are edgemesh, a helpful senior software engineer. Be concise and precise." },
    ];
    view.webview.onDidReceiveMessage(async (m) => {
      if (m.type !== "ask") return;
      history.push({ role: "user", content: m.text });
      view.webview.postMessage({ type: "start" });
      let acc = "";
      try {
        await chatStream(history, (d) => {
          acc += d;
          view.webview.postMessage({ type: "delta", text: d });
        });
      } catch (e: any) {
        view.webview.postMessage({ type: "delta", text: `\n[error: ${e.message || e}]` });
      }
      history.push({ role: "assistant", content: acc });
      view.webview.postMessage({ type: "end" });
    });
  }

  private html(): string {
    return `<!DOCTYPE html><html><head><meta charset="utf-8"/>
<style>
  body{font-family:var(--vscode-font-family);color:var(--vscode-foreground);margin:0;padding:8px;display:flex;flex-direction:column;height:100vh;box-sizing:border-box}
  #log{flex:1;overflow:auto;font-size:13px;line-height:1.45}
  .msg{margin:8px 0;white-space:pre-wrap;word-wrap:break-word}
  .u{color:var(--vscode-textLink-foreground)} .a{opacity:.95}
  #row{display:flex;gap:6px;margin-top:6px}
  #q{flex:1;background:var(--vscode-input-background);color:var(--vscode-input-foreground);border:1px solid var(--vscode-input-border,transparent);padding:6px;border-radius:4px;resize:none}
  button{background:var(--vscode-button-background);color:var(--vscode-button-foreground);border:none;padding:6px 10px;border-radius:4px;cursor:pointer}
</style></head><body>
<div id="log"></div>
<div id="row"><textarea id="q" rows="2" placeholder="Ask edgemesh… (Enter to send)"></textarea><button id="send">Send</button></div>
<script>
  const vscode = acquireVsCodeApi();
  const log = document.getElementById('log'), q = document.getElementById('q');
  let cur = null;
  function add(cls, text){ const d=document.createElement('div'); d.className='msg '+cls; d.textContent=text; log.appendChild(d); log.scrollTop=log.scrollHeight; return d; }
  function ask(){ const t=q.value.trim(); if(!t) return; add('u','› '+t); q.value=''; vscode.postMessage({type:'ask',text:t}); }
  document.getElementById('send').onclick=ask;
  q.addEventListener('keydown',e=>{ if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask();}});
  window.addEventListener('message',e=>{ const m=e.data;
    if(m.type==='start'){ cur=add('a',''); }
    else if(m.type==='delta'&&cur){ cur.textContent+=m.text; log.scrollTop=log.scrollHeight; }
    else if(m.type==='end'){ cur=null; }
  });
</script></body></html>`;
  }
}

export function deactivate() {}
