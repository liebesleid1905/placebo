"""GitHub Copilot CLI adapter (`copilot -p ... --output-format json`).

Event format (Copilot CLI 1.0.x, JSONL, one envelope `{"type", "data", ...}` per line):

- `session.start`          -> `data.copilotVersion`
- `session.auto_mode_resolved` / `assistant.message` -> model
- `assistant.turn_start`   -> one per model turn
- `tool.execution_start`   -> one per tool call (`data.toolName`, `data.arguments`);
                              skill activation is the `skill` tool with `{"skill": "<name>"}`
- `tool.execution_complete`-> `data.toolTelemetry.metrics.context_current_tokens`
- `assistant.message`      -> `data.content` (final answer has an empty `toolRequests`)
- `result`                 -> `exitCode`, `usage.premiumRequests`

Copilot does not report per-request token counts or dollars in headless mode, so
`cost_usd` stays None and `usage.input_tokens` holds the peak context size seen
(a proxy for the tokens the model had to read on its last call). Compare it
across arms, not across agents.
"""

from __future__ import annotations

from pathlib import Path

from placebo_cli.adapters.base import AgentAdapter, ParseState, RunOptions, Watch
from placebo_cli.skills.discovery import home_dir


class CopilotAdapter(AgentAdapter):
    id = "copilot"
    label = "Copilot CLI"
    project_skill_dir = ".github/skills"
    reports_cost = False
    binary_names = ("copilot",)
    binary_env = "PLACEBO_COPILOT_BIN"

    def user_skill_dirs(self) -> list[Path]:
        return [home_dir() / ".copilot" / "skills", home_dir() / ".agents" / "skills"]

    def command(self, workdir: Path, opts: RunOptions) -> tuple[list[str], str | None]:
        b = self.binary()
        if not b:
            raise RuntimeError("Copilot CLI not found (install it or set PLACEBO_COPILOT_BIN)")
        argv = [
            b, "--output-format", "json",
            "--allow-all-tools",       # headless: nobody can answer permission prompts
            "--no-ask-user",
            "--disable-builtin-mcps",  # keep GitHub MCP tools out of the context being measured
            "--no-color",
        ]
        if opts.model:
            argv += ["--model", opts.model]
        argv += list(opts.extra_args)
        return argv, None  # the prompt is appended as `-p <prompt>` (see prompt_argv)

    def prompt_argv(self, prompt: str) -> list[str]:
        return ["-p", prompt]

    def parse_event(self, obj: dict, st: ParseState, watch: Watch) -> None:
        t = obj.get("type")
        d = obj.get("data") if isinstance(obj.get("data"), dict) else {}
        if t == "session.start":
            st.agent_version = d.get("copilotVersion") or st.agent_version
        elif t == "session.auto_mode_resolved":
            st.model = d.get("chosenModel") or st.model
        elif t == "assistant.turn_start":
            st.turns = (st.turns or 0) + 1
        elif t == "tool.execution_start":
            st.tool_calls += 1
            st.activate(watch.match(d.get("toolName"), d.get("arguments")))
        elif t == "tool.execution_complete":
            metrics = ((d.get("toolTelemetry") or {}).get("metrics")) or {}
            ctx = metrics.get("context_current_tokens")
            if isinstance(ctx, (int, float)) and ctx > st.usage.input_tokens:
                st.usage.input_tokens = int(ctx)
        elif t == "assistant.message":
            st.model = d.get("model") or st.model
            if isinstance(d.get("content"), str) and d["content"].strip():
                st.last_text = d["content"]
                if not d.get("toolRequests"):
                    st.final_text = d["content"]
        elif t in ("session.error", "error"):
            msg = d.get("message") or obj.get("message") or t
            st.error = str(msg)[:300]
        elif t == "result":
            code = obj.get("exitCode")
            if isinstance(code, int) and code != 0 and st.error is None:
                st.error = f"copilot exited with code {code}"
