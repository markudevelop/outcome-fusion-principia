# Outcome Fusion Principia Operator

MIT licensed. See [`LICENSE`](LICENSE) and [`CHANGELOG.md`](CHANGELOG.md).

## v0.3.7

- **The release gate actually works now.** It previously crashed on a `str.format`
  bug (unescaped JSON braces) and silently fell back to a heuristic in every
  session. Fixed via a brace-safe formatter.
- **Lazy-impossibility detection** no longer false-fires on the plugin's own
  injected rules; it inspects only Claude's final message.
- **Visible prompt rewrite.** When you submit a prompt, the compiled mission is
  printed to the terminal so you can see how it was rewritten. Your original
  prompt is never replaced — the mission is added as context.
  - `OUTCOME_FUSION_SHOW_MISSION=0` hides it (default on).
  - `OUTCOME_FUSION_SHOW_MISSION_CHARS=4000` caps how much is shown.
- **Network resilience.** `call_deepseek` retries once on a transient timeout
  (`OUTCOME_FUSION_RETRIES`, default 1).
- **Removed the unused `guard_bash.py`** and `OUTCOME_FUSION_RISK_MODE`. The Bash
  guard was never wired into the hooks; the sections below referencing risk
  modes are retained only as history.

## How it works (in one minute)

Outcome Fusion Principia is a local Claude Code plugin that wraps your coding
session in a scientific operating loop, powered by DeepSeek. It runs entirely
through Claude Code hooks — no changes to your code or workflow:

1. **You type a prompt.** A `UserPromptSubmit` hook sends it to DeepSeek, which
   rewrites it into a precise *mission* (objective, constraints, hypotheses,
   verification plan, release criteria). The rewrite is printed in your terminal
   and added to Claude's context — **your original prompt is never replaced.**
2. **Claude works.** `PostToolUse` hooks log every command and auto-record
   verification commands (tests, lint, builds) into a per-session **proof
   ledger**.
3. **Claude tries to stop.** A `Stop` hook runs the **release gate**: DeepSeek
   judges the mission, git diff, transcript, tool log, and proof ledger, then
   returns `PASS` / `FAIL` / `BLOCKED`. A weak result pushes Claude to keep
   going with concrete next actions instead of stopping early.
4. **Completion closure.** Before `PASS`, the gate runs the audit you'd trigger
   by asking *"anything else?"* — if it would reveal missed work, it fails now.
5. **Session isolation + resume.** Every conversation gets its own workspace
   under `.ai/outcome_fusion/sessions/<id>/`, reconnected on `/resume`.

```
prompt ──▶ [DeepSeek mission compiler] ──▶ Claude works ──▶ [DeepSeek release gate]
              shown in terminal              proof ledger        PASS / FAIL / BLOCKED
```

## Install from GitHub

```text
/plugin marketplace add newgene11/outcome-fusion-principia
/plugin install outcome-fusion-principia@outcome-fusion-local
```

Then set your DeepSeek key (the plugin also accepts `ANTHROPIC_API_KEY` /
`ANTHROPIC_AUTH_TOKEN` against an Anthropic-compatible endpoint):

```bash
export DEEPSEEK_API_KEY="your_key_here"
export OUTCOME_FUSION_MODEL="deepseek-v4-pro"   # optional
```

Without a key (or if DeepSeek is unreachable) the plugin degrades gracefully to
a built-in heuristic mission and gate — it never blocks your session.

## Testing

Pure helpers and the two v0.3.7 regression fixes are covered by `pytest`:

```bash
pip install pytest
python -m pytest -q
```

CI runs the suite on every push (`.github/workflows/tests.yml`).

## Configuration reference

| Env var | Default | Effect |
|---------|---------|--------|
| `DEEPSEEK_API_KEY` | — | API key (falls back to `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN`) |
| `OUTCOME_FUSION_ENABLED` | `1` | Master switch for all hooks |
| `OUTCOME_FUSION_MODEL` | `deepseek-v4-pro` | Model id |
| `OUTCOME_FUSION_SHOW_MISSION` | `1` | Print the rewritten mission in the terminal |
| `OUTCOME_FUSION_SHOW_MISSION_CHARS` | `4000` | Max chars of mission shown |
| `OUTCOME_FUSION_TERMINAL_LOG` | `1` | Show compact terminal status lines |
| `OUTCOME_FUSION_RETRIES` | `1` | DeepSeek retries on transient errors |
| `OUTCOME_FUSION_MAX_CONTINUES` | `5` | Max forced continuations before manual review |
| `OUTCOME_FUSION_EFFORT` | `high` | Reasoning effort sent to the model |

Add `nofusion` anywhere in a prompt to skip the compiler for that turn.

# Outcome Fusion Principia Operator v3.6

Session scoped and resume aware. Each Claude Code conversation gets its own folder under `.ai/outcome_fusion/sessions/<session>/`, so multiple tasks in the same repo do not overwrite each other. On `/resume`, the SessionStart hook reloads the same mission, proof ledger, review, closure, and tool log when Claude provides the same session id or transcript path.

Fast paths:

```text
.ai/outcome_fusion/current_session.txt
.ai/outcome_fusion/sessions/<session>/mission.md
.ai/outcome_fusion/sessions/<session>/proof.md
.ai/outcome_fusion/sessions/<session>/review.md
.ai/outcome_fusion/sessions/<session>/closure.md
.ai/outcome_fusion/sessions/<session>/tool_log.md
```

Convenience mirrors are also written as `latest_mission.md`, `latest_review.md`, `latest_closure.md`, and `latest_tool_log.md`, but session folders are the source of truth.

Terminal visible DeepSeek mission and release gate messages. Bash guard removed.

Set `OUTCOME_FUSION_TERMINAL_LOG=1` or leave unset to show compact terminal messages. Set it to `0` to hide them.

# Outcome Fusion Principia Operator v3.1

Outcome Fusion Principia Operator is a local Claude Code plugin that uses DeepSeek directly.

It is designed for autonomous execution without babysitting:

1. First principles before solutions.
2. Remove what does not need to exist.
3. Verify claims instead of guessing.
4. Break lazy impossibility claims.
5. Generate non obvious paths tied to experiments.
6. Push Claude until release ready or blocked by evidence.
7. Operator mode by default: no approval spam for normal coding work.

## What changed from v3

v3 had conservative safety prompts and asked before dangerous categories.

v3.1 changes the default to **operator mode**:

```bash
export OUTCOME_FUSION_RISK_MODE="operator"
```

Operator mode lets Claude Code execute normal repo work without asking you small questions.
It only blocks catastrophic local wipe commands and obvious secret dumping by default.

Strict mode is still available:

```bash
export OUTCOME_FUSION_RISK_MODE="strict"
```

Full local responsibility mode is also available:

```bash
export OUTCOME_FUSION_RISK_MODE="off"
```

That disables the Bash guard completely. Use it only when you accept the risk.

## Files created in each repo

```text
.ai/outcome_fusion/current_session.txt
.ai/outcome_fusion/sessions/<session>/mission.md
.ai/outcome_fusion/sessions/<session>/proof.md
.ai/outcome_fusion/sessions/<session>/review.md
.ai/outcome_fusion/sessions/<session>/closure.md
.ai/outcome_fusion/sessions/<session>/tool_log.md
.ai/outcome_fusion/sessions/<session>/last_error.txt
.ai/outcome_fusion/memory.md
.ai/outcome_fusion/latest_mission.md
.ai/outcome_fusion/latest_review.md
```

## Install

```bash
unzip outcome_fusion_principia_operator_v3_1.zip
cd outcome_fusion_principia_operator_v3_1
./install_local.sh
```

Then in Claude Code:

```text
/plugin install outcome-fusion-principia@outcome-fusion-local
/reload-plugins
```

## DeepSeek setup

```bash
export DEEPSEEK_API_KEY="your_key_here"
export OUTCOME_FUSION_MODEL="deepseek-v4-pro"
export OUTCOME_FUSION_RISK_MODE="operator"
```

Optional effort:

```bash
export OUTCOME_FUSION_EFFORT="high"
```

## How it works

### 1. Prompt compiler

You write normally:

```text
fix the sync and make it reliable
```

The UserPromptSubmit hook sends your prompt to DeepSeek and creates:

```text
.ai/outcome_fusion/mission.md
```

Claude receives the mission as extra context. Your original prompt is not replaced.

### 2. Scientific proof ledger

The plugin maintains:

```text
.ai/outcome_fusion/proof.md
```

Claude is pushed to record:

```text
claim
evidence
method
result
confidence
remaining risk
```

### 3. Release gate

When Claude tries to stop, DeepSeek reviews:

```text
mission
git diff
recent transcript
tool log
proof ledger
Claude final message
```

If the result is weak, Claude gets pushed to continue.

### 4. Impossible breaker

If Claude says:

```text
impossible
cannot
not realistic
no edge
won't work
doesn't exist
```

The gate forces proof or a falsification experiment.

## Modes

### Operator mode

Best default for your workflow.

```bash
export OUTCOME_FUSION_RISK_MODE="operator"
```

Behavior:

```text
normal coding commands: allowed
builds/tests/lint/git diff/search: allowed
normal file edits: allowed
catastrophic local wipe: blocked
obvious secret dumping: blocked
```

### Strict mode

More confirmations.

```bash
export OUTCOME_FUSION_RISK_MODE="strict"
```

### Off mode

No Bash guard.

```bash
export OUTCOME_FUSION_RISK_MODE="off"
```

This is dangerous. The plugin will not stop destructive commands.

## Core doctrine

```text
Do not ask low value questions.
Make reversible assumptions.
Act.
Verify.
Remove unnecessary parts.
Break lazy impossibility claims.
Keep going until release ready or blocked by evidence.
```

## Commands

```text
/principia
/status
/reset
```

## Skills included

```text
principia
quant-scientist
```

Use `/principia` when you want to force the mode manually.


## v0.3.2 fix
Removed duplicate manifest hooks reference. Claude Code automatically loads standard hooks/hooks.json.


## v3.3 note

PreToolUse Bash guard is removed. OUTCOME_FUSION_RISK_MODE is no longer needed for command blocking. The plugin still compiles missions, logs tools, and runs the release gate.


## v3.5 Completion Closure

This version adds a final gap audit before PASS. The release gate should not return PASS if Claude would later answer "yes, I missed X" to a normal "anything else?" question.

On PASS it writes `.ai/outcome_fusion/closure.md` with the release state, verified items, open non blockers, and the reason stopping is justified.

If the user asks "anything else?", "what did you miss?", or similar, the prompt compiler injects the closure state so Claude must answer from verified facts, not invent new scope.


## v3.6 Session Isolation and Resume

Multiple Claude Code sessions in the same repo no longer overwrite each other. The plugin uses Claude hook payload fields such as `session_id` and `transcript_path` to create a stable session workspace.

On `/resume`, the SessionStart hook reloads the matching workspace. If Claude changes the session id but keeps the transcript path, the plugin reconnects using transcript metadata. If neither exists, it falls back to the repo's `current_session.txt` and then the newest session with a mission.

Use `/status` to inspect the active session.
