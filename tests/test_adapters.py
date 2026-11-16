"""Adapter parsing tests.

The fixtures below are synthetic: hand-written to match each agent's documented
JSON event format. When you capture a real trace, add it under tests/fixtures/
and a test that replays it.
"""

from __future__ import annotations

import json

from placebo_cli.adapters.base import ParseState, Watch
from placebo_cli.adapters.claude_code import ClaudeCodeAdapter
from placebo_cli.adapters.codex import CodexAdapter

CLAUDE_EVENTS = [
    {"type": "system", "subtype": "init", "model": "claude-x", "claude_code_version": "2.1.281",
     "skills": ["tdd-guard", "pdf"]},
    {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Let me check the skill."},
        {"type": "tool_use", "name": "Skill", "input": {"skill": "tdd-guard"}},
    ]}},
    {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q"}},
    ]}},
    {"type": "result", "subtype": "success", "is_error": False, "num_turns": 4, "total_cost_usd": 0.1234,
     "result": "All tests pass.",
     "usage": {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 3000, "cache_creation_input_tokens": 400}},
]

CODEX_EVENTS = [
    {"type": "thread.started", "thread_id": "abc"},
    {"type": "item.completed", "item": {"id": "1", "type": "command_execution",
                                         "command": "cat .agents/skills/tdd-guard/SKILL.md", "exit_code": 0,
                                         "aggregated_output": "---\nname: tdd-guard"}},
    {"type": "item.completed", "item": {"id": "2", "type": "command_execution",
                                         "command": "ls", "aggregated_output": ".agents/skills/pdf/SKILL.md"}},
    {"type": "item.completed", "item": {"id": "3", "type": "agent_message", "text": "Done."}},
    {"type": "turn.completed", "usage": {"input_tokens": 5000, "cached_input_tokens": 4000, "output_tokens": 300}},
]


def replay(adapter, events, watch):
    st = ParseState()
    for e in events:
        adapter.parse_event(json.loads(json.dumps(e)), st, watch)
    return st


def test_claude_parsing():
    st = replay(ClaudeCodeAdapter(), CLAUDE_EVENTS, Watch(["tdd-guard", "pdf"]))
    assert st.activated == ["tdd-guard"]
    assert st.visible_skills == ["tdd-guard", "pdf"]
    assert st.tool_calls == 2
    assert st.cost_usd == 0.1234
    assert st.usage.total == 100 + 50 + 3000 + 400
    assert st.final_text == "All tests pass."
    assert st.agent_version == "2.1.281"


def test_codex_parsing_counts_commands_not_output():
    st = replay(CodexAdapter(), CODEX_EVENTS, Watch(["tdd-guard", "pdf"]))
    assert st.activated == ["tdd-guard"]  # `ls` output mentioning pdf is not an activation
    assert st.tool_calls == 2
    assert st.usage.input_tokens == 1000 and st.usage.cache_read_tokens == 4000
    assert st.last_text == "Done."
    assert st.cost_usd is None


def test_claude_real_trace_not_logged_in():
    """Replays real Claude Code 2.1.281 output (sanitized) from an unauthenticated run."""
    from pathlib import Path

    events = [json.loads(l) for l in (Path(__file__).parent / "fixtures" / "claude_code_2.1.281_not_logged_in.jsonl")
              .read_text(encoding="utf-8").splitlines() if l.strip()]
    st = replay(ClaudeCodeAdapter(), events, Watch(["greeting-style"]))
    assert st.agent_version == "2.1.281"
    assert st.model == "claude-haiku-4-5-20251001"
    assert "greeting-style" in st.visible_skills  # project-level skill is visible headless
    assert st.activated == []
    assert st.error and "Not logged in" in st.error
    assert st.cost_usd == 0 and st.tool_calls == 0


def test_watch_matches_paths_and_plugin_prefixes():
    w = Watch(["my-skill"])
    assert w.match("Read", {"file_path": "C:\\repo\\.claude\\skills\\my-skill\\SKILL.md"}) == ["my-skill"]
    assert w.match("Skill", {"skill": "plugin-x:my-skill"}) == ["my-skill"]
    assert w.match("Bash", {"command": "ls skills"}) == []


def test_claude_command_uses_stdin_and_budget(monkeypatch, tmp_path):
    from placebo_cli.adapters.base import RunOptions

    monkeypatch.setenv("PLACEBO_CLAUDE_BIN", "claude-bin")
    argv, stdin = ClaudeCodeAdapter().command(tmp_path, RunOptions(model="sonnet", budget_usd=0.5))
    assert argv[0] == "claude-bin" and "-p" in argv and stdin == ""
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert argv[argv.index("--max-budget-usd") + 1] == "0.50"
    assert "--no-session-persistence" in argv


def _load_fixture(name):
    from pathlib import Path

    path = Path(__file__).parent / "fixtures" / name
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_copilot_real_trace_plain_file_read():
    """Replays real Copilot CLI 1.0.109 output (sanitized): one `view` call, no skills."""
    from placebo_cli.adapters.copilot import CopilotAdapter

    st = replay(CopilotAdapter(), _load_fixture("copilot_1.0.109_read_file.jsonl"), Watch(["secret-word"]))
    assert st.agent_version == "1.0.109"
    assert st.model == "gpt-6-luna"
    assert st.tool_calls == 1 and st.turns == 2
    assert st.activated == []
    assert st.final_text == "hello"
    assert st.usage.input_tokens == 16187  # peak context size, the only token signal Copilot emits
    assert st.cost_usd is None and st.error is None


def test_copilot_real_trace_skill_activation():
    """Replays a real run where Copilot loaded a project skill through its `skill` tool."""
    from placebo_cli.adapters.copilot import CopilotAdapter

    st = replay(CopilotAdapter(), _load_fixture("copilot_1.0.109_skill_activation.jsonl"), Watch(["secret-word", "other"]))
    assert st.activated == ["secret-word"]
    assert st.tool_calls == 1
    assert st.final_text == "PLACEBO42"
    assert st.error is None


def test_copilot_nonzero_exit_is_an_error():
    from placebo_cli.adapters.copilot import CopilotAdapter

    st = replay(CopilotAdapter(), [{"type": "result", "exitCode": 1}], Watch())
    assert st.error and "code 1" in st.error


def test_copilot_command_and_registry(monkeypatch, tmp_path):
    from placebo_cli.adapters.base import RunOptions
    from placebo_cli.adapters.copilot import CopilotAdapter
    from placebo_cli.adapters.registry import DETECT_ONLY, get_adapter

    monkeypatch.setenv("PLACEBO_COPILOT_BIN", "copilot-bin")
    a = CopilotAdapter()
    argv, stdin = a.command(tmp_path, RunOptions(model="gpt-x"))
    assert argv[0] == "copilot-bin" and stdin is None
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--model") + 1] == "gpt-x"
    assert "--allow-all-tools" in argv and "--no-ask-user" in argv
    assert a.prompt_argv("do it") == ["-p", "do it"]
    assert a.project_skill_dir == ".github/skills"
    assert get_adapter("github-copilot").id == "copilot"
    assert "copilot" not in DETECT_ONLY
