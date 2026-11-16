# Experiment: does a conventions skill help Copilot CLI?

A real `placebo ab` run, 2026-11-16. Small and synthetic on purpose: it shows the tool working end to
end and what its output looks like, not that skills in general help.

**Setup**

- Agent: GitHub Copilot CLI (version 1.0.112 in the run report), model `gpt-6-luna` (auto-selected)
- Project: a tiny Python package `acme` with an exception class and **one example module that follows the conventions** (`acme/add.py`)
- Skill under test: [`acme-conventions`](skill/acme-conventions/SKILL.md), six rules (one module per function, `__all__`, type hints, Google-style docstring, raise `AcmeError`, add a test file)
- 10 tasks: "add function X" (`slugify`, `clamp`, `chunk`, `parse_duration`, `is_palindrome`, `word_count`, `median`, `truncate`, `roman`, `flatten`)
- Each task passes only if **two** checks pass: a functional check (behaviour and `AcmeError` on bad input) and a convention check (module layout, `__all__`, type hints, docstring, test file)
- 3 arms x 10 tasks x 2 trials = 60 runs, 3 in parallel, randomized order, `--seed 1`
- Both checks were validated first with a reference solution for every task, plus a negative control (correct code without the conventions fails only the convention check): `verify_refs.py`

Reproduce: `python build.py && python verify_refs.py`, then
`placebo ab skill/acme-conventions --agent copilot --repo proj --tasks tasks.yaml --trials 2 --parallel 3 --seed 1`
(about 60 premium requests and 45 minutes).

**Result**

| Arm | Pass rate | Runs | Skill used | Context tokens/run | Time/run |
|---|---|---|---|---|---|
| baseline (no skill) | 25% (5/20) | 20 | n/a | 17,455 | 42 s |
| treatment (the skill) | **100% (20/20)** | 20 | 100% | 17,313 | 40 s |
| sham (same name and description, inert body) | 70% (14/20) | 20 | 100% | 18,558 | 54 s |

| Comparison | Δ pass rate | 95% CI |
|---|---|---|
| treatment vs baseline | +75 pp | +50 .. +95 pp |
| treatment vs sham | +30 pp | +5 .. +60 pp |
| sham vs baseline | +45 pp | +20 .. +70 pp |

Verdict: **HELPS**. Per task (passes out of 2): the skill passed 2/2 on all ten tasks. Baseline passed 2/2 only on
`clamp`, 1/2 on `median`, `roman` and `slugify`, and 0/2 on the other six.

**How to read it**

- The skill clearly helps on this project: it never failed, and the gap to baseline is large and the interval excludes zero.
- **Most of the baseline gap is not the skill's body.** The sham arm has the real name and description, whose text lists
  the conventions topics ("module, typing, docstring, error and test conventions"). Copilot loaded the sham skill in every
  run, and that was enough to lift it from 25% to 70%, probably because it made the agent look at the example module.
  Only +30 pp (CI +5..+60) is attributable to the actual rules. Without a sham arm this experiment would have credited
  the skill with the full +75 pp. That is the reason placebo has one.
- The baseline failures were mostly convention misses (missing docstring sections, module named differently from the function) and
  `ValueError` instead of `AcmeError`, not wrong logic.
- The repo had an example to imitate. A repo without one would probably show a bigger content effect; this was not tested.
- Caveats: 10 tasks, 2 trials each, one model, one agent, a synthetic project, tasks written by the tool's author. Treat the sizes as indicative. The intervals are wide.
- Copilot reports neither cost nor token usage, so the token column is the peak context size seen by the agent.
