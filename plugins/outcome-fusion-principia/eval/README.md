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

8 labelled end-states: 3 genuinely done (incl. one legitimately blocked on a
missing prod credential) and 5 with planted release-critical defects —
claims-without-evidence, a placeholder `TODO`, a lazy "impossible" refusal, a
"tests pass" claim over a syntax error, and an unsupported "10x faster".

## Result (DeepSeek judge, v0.3.8)

| Metric | Without plugin | With plugin |
|--------|----------------|-------------|
| Defective completions caught | 0 / 5 | **5 / 5** |
| Genuinely-done handled correctly | n/a (all ship) | **3 / 3** (2 PASS, 1 correct BLOCK) |

The five broken completions a normal agent would have shipped were each returned
with a specific blocker; the genuinely-done work passed.

### Caveats

- n = 8, synthetic scenarios; single judge model; verdicts are mildly stochastic.
- v0.3.8 adds a JSON-parse retry (`call_deepseek_json`) because the judge
  occasionally returns malformed/truncated JSON; on an unrecoverable parse the
  plugin falls back to the keyword heuristic, which **degrades to "allow stop"**
  for has-proof / no-refusal states rather than wrongly blocking.
- A stronger future test: 30–50 scenarios × multiple trials for confidence
  intervals, plus a true task-success A/B (same coding tasks solved with vs.
  without the plugin, graded by hidden tests).
