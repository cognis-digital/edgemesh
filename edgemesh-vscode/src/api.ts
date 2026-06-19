// Thin client for the edgemesh OpenAI-compatible gateway. Uses global fetch
// (VSCode ships a modern Node runtime), so no third-party HTTP dependency.
import * as vscode from "vscode";

export type Msg = { role: "system" | "user" | "assistant"; content: string };

function cfg() {
  const c = vscode.workspace.getConfiguration("edgemesh");
  return {
    gateway: (c.get<string>("gateway") || "http://127.0.0.1:8780").replace(/\/$/, ""),
    model: c.get<string>("model") || "",
  };
}

export async function resolveModel(): Promise<string> {
  const { gateway, model } = cfg();
  if (model) return model;
  const res = await fetch(`${gateway}/v1/models`);
  if (!res.ok) throw new Error(`gateway /v1/models -> HTTP ${res.status}`);
  const data = (await res.json()) as { data?: { id: string }[] };
  const first = data.data?.[0]?.id;
  if (!first) throw new Error("no models available from the gateway");
  return first;
}

export function gateway(): string {
  return cfg().gateway;
}

// One-shot completion.
export async function chat(messages: Msg[]): Promise<string> {
  const model = await resolveModel();
  const res = await fetch(`${gateway()}/v1/chat/completions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model, messages }),
  });
  if (!res.ok) throw new Error(`chat -> HTTP ${res.status}: ${await res.text()}`);
  const body = (await res.json()) as any;
  return body.choices?.[0]?.message?.content ?? "(no reply)";
}

// Streaming completion (SSE). Calls onDelta for each token chunk.
export async function chatStream(messages: Msg[], onDelta: (s: string) => void): Promise<void> {
  const model = await resolveModel();
  const res = await fetch(`${gateway()}/v1/chat/completions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model, messages, stream: true }),
  });
  if (!res.ok || !res.body) throw new Error(`chat -> HTTP ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() || "";
    for (const line of lines) {
      const t = line.trim();
      if (!t.startsWith("data:")) continue;
      const payload = t.slice(5).trim();
      if (payload === "[DONE]") return;
      try {
        const delta = JSON.parse(payload).choices?.[0]?.delta?.content;
        if (delta) onDelta(delta);
      } catch {
        /* ignore keep-alive / partial frames */
      }
    }
  }
}
