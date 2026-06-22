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
| `/reset` | Archive/clear the active session workspace (keeps project memory) |

**Skills** — `principia` (general first-principles execution) and
`quant-scientist` (trading/quant claims: leakage, costs, capacity, walk-forward).

**Agents** — `first-principles-skeptic`, `verification-scientist`, `simplifier`,
`quant-research-auditor`.

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
```

Session folders are the source of truth; `latest_*.md` mirrors are written at the
root for convenience.

---

## Testing

```bash
pip install pytest
python -m pytest -q
```

The suite covers the pure helpers plus regression locks for the brace-safe
prompt formatter and the lazy-detection scoping. CI runs it on every push.

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
