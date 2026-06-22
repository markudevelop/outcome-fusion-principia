# Evaluation

A reproducible measurement of what the plugin actually buys you: the
**release-gate's ability to catch defective "done" states.**

## Why this is the right thing to measure

The plugin's core mechanism is a judge model that decides whether the agent is
allowed to stop. So the cleanest empirical question is:

> When an agent declares a task "done", how often is that completion actually
> defective — and does the gate catch it?

- **Without the plugin**, an agent stops the moment it says "done", so it accepts
  every completion: **0 defects caught.**
- **With the plugin**, the gate (DeepSeek) reviews the mission, diff, proof
  ledger, and final message and returns `PASS` / `FAIL` / `BLOCKED`.

This measures gate *discrimination*, not end-to-end task success. The set is
small and synthetic — treat it as a reproducible demonstration, not a benchmark.

## Run it

```bash
export DEEPSEEK_API_KEY=...      # or ANTHROPIC_API_KEY against a compatible endpoint
python plugins/outcome-fusion-principia/eval/run_eval.py
```

## Scenarios

13 labelled end-states across two domains:

- **Engineering (8):** 3 genuinely done (incl. one legitimately blocked on a
  missing prod credential) and 5 with planted defects — claims-without-evidence,
  a placeholder `TODO`, a lazy "impossible" refusal, a "tests pass" claim over a
  syntax error, and an unsupported "10x faster".
- **Generic / non-engineering (5):** a correct sourced fact and a properly hedged
  research answer (good); a factually wrong date, an unsourced medical overclaim,
  and an answer that ignores the question's required dimensions (defects).

The generic set proves the gate is **universal** — it judges research, factual,
and analytical answers on sourcing, accuracy, and completeness, not on code.

Filter by domain with `OF_EVAL_DOMAIN=eng` or `OF_EVAL_DOMAIN=generic`.

## Result (DeepSeek judge)

| Domain | Defects caught (vs 0 without plugin) | Good handled |
|--------|--------------------------------------|--------------|
| Engineering | **5 / 5** | 3 / 3 |
| Generic | **3 / 3** | 2 / 2 |

Defective completions a normal agent would have shipped were each returned with a
specific blocker; genuinely-done work passed in both domains.

### Caveats

- Small synthetic n; single judge model; verdicts are mildly stochastic.
  `OUTCOME_FUSION_GATE_VOTES > 1` runs self-consistency voting to reduce variance.
- On an unrecoverable JSON parse the plugin falls back to the keyword heuristic,
  which **degrades to "allow stop"** for has-proof / no-refusal states rather than
  wrongly blocking.

## Planned: task-success A/B

The eval above measures the gate's *accept/reject discrimination*. The stronger
test is an end-to-end A/B: take N tasks with objective graders (hidden unit tests
for code; a fixed answer key / rubric for factual and research tasks); solve each
twice — once with the plugin's hooks disabled (`OUTCOME_FUSION_ENABLED=0`), once
enabled — and compare graded success rates. This needs an agent-runner harness
and per-task graders, so it is tracked as the next milestone rather than shipped
here (no stub is included, to avoid a non-functional placeholder).
