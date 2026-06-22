# Outcome Fusion Principia

[![tests](https://github.com/markudevelop/outcome-fusion-principia/actions/workflows/tests.yml/badge.svg)](https://github.com/markudevelop/outcome-fusion-principia/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Model fusion for Claude Code.** One model *builds* (Claude). A different model
*judges* the result (DeepSeek). Because the work is graded by a separate mind
from the one that wrote it, the agent can't rubber-stamp its own output or quit
early — and the result improves.

> One model builds. Another model judges. The result is better than either alone.

It runs entirely through Claude Code hooks. No changes to your code or workflow:
your prompt becomes a precise mission, your work is checked against a proof
ledger, and a release gate decides whether you're actually done.

---

## How it works

```
your prompt ─▶ [DeepSeek mission compiler] ─▶ Claude works ─▶ [DeepSeek release gate]
                  shown in your terminal          proof ledger      PASS / FAIL / BLOCKED
```

1. **Mission compiler** (`UserPromptSubmit`) — your prompt is rewritten by
   DeepSeek into a precise, testable mission: objective, constraints,
   hypotheses, a verification plan, and release criteria. The rewrite is printed
   in your terminal, and **your original prompt is never replaced** — the mission
   is added as context.
2. **Proof ledger** (`PostToolUse`) — every command is logged, and verification
   commands (tests, lint, builds) are recorded into a per-session ledger of
   claim → evidence → method → result → confidence → remaining risk.
3. **Release gate** (`Stop`) — when Claude tries to finish, DeepSeek judges the
   mission, git diff, transcript, tool log, and proof ledger, returning
   `PASS` / `FAIL` / `BLOCKED`. A weak result pushes Claude to continue with
   concrete next actions instead of stopping early.
4. **Impossibility breaker** — a lazy "this is impossible / can't be done" is met
   with a demand for proof or a falsification test, not accepted at face value.
5. **Completion closure** — before `PASS`, the gate runs the audit you'd trigger
   by asking *"anything else?"*. If that would reveal missed work, it fails now.
6. **Session isolation + resume** — each conversation gets its own workspace
   under `.ai/outcome_fusion/sessions/<id>/`, reconnected on `/resume`.

If DeepSeek has no key or is unreachable, the plugin degrades gracefully to a
built-in heuristic mission and gate — it never blocks your session.

---

## Install

In Claude Code:

```text
/plugin marketplace add markudevelop/outcome-fusion-principia
/plugin install outcome-fusion-principia@outcome-fusion
```

Set your key (DeepSeek, or any Anthropic-compatible endpoint):

```bash
export DEEPSEEK_API_KEY="your_key_here"
# optional:
export OUTCOME_FUSION_MODEL="deepseek-v4-pro"
```

The key also resolves from `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` against
`DEEPSEEK_ANTHROPIC_BASE_URL` (default `https://api.deepseek.com/anthropic`).

---

## Configuration

| Env var | Default | Effect |
|---------|---------|--------|
| `DEEPSEEK_API_KEY` | — | API key (falls back to `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN`) |
| `OUTCOME_FUSION_ENABLED` | `1` | Master switch for all hooks |
| `OUTCOME_FUSION_MODEL` | `deepseek-v4-pro` | Model id |
| `OUTCOME_FUSION_SHOW_MISSION` | `1` | Print the rewritten mission in the terminal |
| `OUTCOME_FUSION_SHOW_MISSION_CHARS` | `4000` | Max chars of mission shown |
| `OUTCOME_FUSION_TERMINAL_LOG` | `1` | Show compact terminal status lines |
| `OUTCOME_FUSION_RETRIES` | `1` | DeepSeek retries on a transient error |
| `OUTCOME_FUSION_GATE_VOTES` | `1` | Perspective-diverse judge votes, aggregated to a majority verdict. In a small A/B, `3` cut false-blocks 2/5→0/5 at 3× cost — recommended for higher-stakes turns. See [`docs/MODEL_FUSION.md`](plugins/outcome-fusion-principia/docs/MODEL_FUSION.md) |
| `OUTCOME_FUSION_JSON_RETRIES` | `1` | Re-asks the judge once if its JSON does not parse |
| `OUTCOME_FUSION_MAX_CONTINUES` | `5` | Max forced continuations before manual review |
| `OUTCOME_FUSION_EFFORT` | `high` | Reasoning effort sent to the model |

Add `nofusion` anywhere in a prompt to skip the compiler for that turn.

---

## Commands, skills & agents

**Commands**

| Command | Purpose |
|---------|---------|
| `/principia` | Force the operator mode manually on the current task |
| `/status` | Show the active session's mission, blocker, evidence, next test |
| `/cost` | Summarise DeepSeek usage (calls, tokens, latency) for the session |
| `/reset` | Archive/clear the active session workspace (keeps project memory) |

**Skills** — `principia` (general first-principles execution), `quant-scientist`
(trading/quant claims: leakage, costs, capacity, walk-forward), and
`research-scientist` (research, factual, writing, and analytical claims: sources,
citations, cross-checks).

**Agents** — `first-principles-skeptic`, `verification-scientist`, `simplifier`,
`quant-research-auditor`, and `evidence-auditor` (sourcing/accuracy/completeness
of non-code work).

---

## Universal scope

The loop is not code-only. The mission compiler and the judge are told the task
may be **engineering, research, writing, analysis, factual Q&A, planning, or a
decision**, and to apply the same standard with task-appropriate evidence: code →
builds/tests/runs; research/factual → sources, citations, calculations,
cross-checks; writing/analysis → the stated requirements and accuracy. It never
demands a git diff or tests for a non-code task. (See the `generic` set in the
eval for measured proof.)

---

## Files it creates per repo

```text
.ai/outcome_fusion/current_session.txt
.ai/outcome_fusion/memory.md                       # lessons, shared across sessions
.ai/outcome_fusion/sessions/<id>/mission.md
.ai/outcome_fusion/sessions/<id>/proof.md
.ai/outcome_fusion/sessions/<id>/review.md
.ai/outcome_fusion/sessions/<id>/closure.md
.ai/outcome_fusion/sessions/<id>/tool_log.md
.ai/outcome_fusion/sessions/<id>/metrics.jsonl     # per-call tokens + latency
```

Session folders are the source of truth; `latest_*.md` mirrors are written at the
root for convenience.

---

## Testing

```bash
pip install pytest
python -m pytest -q
```

The suite (46 tests) covers the pure helpers, regression locks for the
brace-safe formatter / JSON-parse robustness / lazy-detection scoping, and an
**integration suite** (`test_integration.py`) that verifies the whole plugin is
internally consistent (manifest ↔ files, valid hook events) and that the hooks
run together end-to-end offline. CI runs it on every push. Tests live with the
plugin at `plugins/outcome-fusion-principia/tests/`.

---

## Does it actually help? (evaluation)

A reproducible benchmark ships inside the plugin at
[`plugins/outcome-fusion-principia/eval/`](plugins/outcome-fusion-principia/eval/).
It feeds the shipped release gate labelled end-states — some genuinely done, some
with planted release-critical defects — and measures how many defects the gate
catches versus the no-plugin baseline (which catches 0, since an agent stops the
moment it says "done").

Latest run (DeepSeek judge, 13 scenarios), vs. the no-plugin baseline of 0:

| Domain | Defects caught | Good handled |
|--------|----------------|--------------|
| Engineering (code) | **5 / 5** | 2–3 / 3 |
| Generic (research/factual/analysis) | **3 / 3** | 2 / 2 |
| **All** | **8 / 8** | 4–5 / 5 |

The strong, repeatable signal is **8/8 defects caught** — completions a normal
agent would have shipped (a wrong fact, an unsourced overclaim, an answer that
ignores the question, untested code claimed as done) are each returned with a
specific blocker. The honest cost: the judge **occasionally false-blocks a
genuinely-done item** (~1 in 5 good cases in one run, 0 in another) — voting
(`OUTCOME_FUSION_GATE_VOTES>1`) reduces that variance. This measures the gate's
discrimination, not end-to-end task success; see the eval README and the planned
A/B.

---

## Development

The repo doubles as a local marketplace. To run an unreleased version from a
checkout:

```bash
./install_local.sh          # registers this directory as a marketplace
```

Then install `outcome-fusion-principia@outcome-fusion` and use `/reload-plugins`.

See [`CHANGELOG.md`](CHANGELOG.md) for version history.

## License

MIT — see [`LICENSE`](LICENSE).
