"""A senior-engineer coding agent that runs on edgemesh's own models.

It feeds the developer toolbelt (``edgemesh.devtools``) to any tool-calling model
behind the gateway and runs the classic loop: think -> call tools -> observe ->
repeat, until the task is done. Because it points at edgemesh's ``/v1`` endpoint,
the same agent runs on the local Cognis fleet, Ollama, llama.cpp, vLLM, or a
hosted API — whatever the cluster is fronting.

Pure standard library (urllib + json).
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field

from edgemesh.devtools import Toolbelt, dispatch, openai_tools

SYSTEM_PROMPT = """\
You are edgemesh-dev, a meticulous senior software engineer working inside a real \
codebase. You have tools to read, search, write and edit files, run shell commands \
and tests, and drive git. Work like a careful staff engineer:

- Investigate before you change: read the relevant files and search the tree first.
- Make the smallest correct change; match the surrounding code's style and conventions.
- After editing, run the tests (run_tests) or a targeted command to verify your work.
- Use git deliberately: check git_status/git_diff before committing; write clear,
  conventional commit messages; never force-push or rewrite shared history unasked.
- If something fails, read the error and fix the root cause — don't paper over it.
- Be concise. When the task is genuinely complete and verified, reply with a short \
summary of what you changed and the verification result, and do NOT call more tools.
"""


@dataclass
class AgentResult:
    final: str
    steps: int
    tool_calls: list[dict] = field(default_factory=list)
    ok: bool = True


def _chat(base_url: str, payload: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


class Agent:
    """Drive a tool-calling model through a task against a workspace."""

    def __init__(self, model: str, base_url: str = "http://127.0.0.1:8780",
                 root: str = ".", max_steps: int = 24, temperature: float = 0.1,
                 on_event=None) -> None:
        self.model = model
        self.base_url = base_url
        self.belt = Toolbelt(root)
        self.max_steps = max_steps
        self.temperature = temperature
        self.on_event = on_event or (lambda kind, data: None)

    def run(self, task: str, extra_system: str = "") -> AgentResult:
        system = SYSTEM_PROMPT + (f"\n\n{extra_system}" if extra_system else "")
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": task}]
        tools = openai_tools()
        all_calls: list[dict] = []

        for step in range(1, self.max_steps + 1):
            payload = {"model": self.model, "messages": messages, "tools": tools,
                       "tool_choice": "auto", "temperature": self.temperature}
            try:
                resp = _chat(self.base_url, payload)
            except Exception as exc:  # noqa: BLE001
                return AgentResult(final=f"gateway/model call failed: {exc}", steps=step,
                                   tool_calls=all_calls, ok=False)

            choice = (resp.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            calls = msg.get("tool_calls") or []

            # No tool calls -> the model is done.
            if not calls:
                final = msg.get("content") or "(no content returned)"
                self.on_event("final", {"content": final})
                return AgentResult(final=final, steps=step, tool_calls=all_calls, ok=True)

            # Record the assistant turn, then execute each requested tool.
            messages.append({"role": "assistant", "content": msg.get("content") or "",
                             "tool_calls": calls})
            for call in calls:
                fn = call.get("function") or {}
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                self.on_event("tool", {"name": name, "args": args, "step": step})
                result = dispatch(self.belt, name, args)
                all_calls.append({"name": name, "args": args, "result_preview": result[:200]})
                messages.append({"role": "tool", "tool_call_id": call.get("id", name),
                                 "name": name, "content": result})

        return AgentResult(final="reached max steps without finishing", steps=self.max_steps,
                           tool_calls=all_calls, ok=False)


__all__ = ["Agent", "AgentResult", "SYSTEM_PROMPT"]
