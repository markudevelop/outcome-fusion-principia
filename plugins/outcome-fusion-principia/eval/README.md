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

**38 labelled end-states across four domains.** The advanced set is built so that
a keyword-matching judge gets it *wrong*: the surface signals (green tests, a
confident final message, a cited source) point the opposite way from the truth.

- **Engineering (8)** — the original set: 3 genuinely done (incl. one legitimately
  blocked on a missing prod credential) and 5 planted defects.
- **Advanced (15)** — tests that pass while proving nothing:
  a test that calls the function and asserts nothing; `3 passed, 12 skipped`
  reported as green; a test that asserts the *bug*; a flaky test rerun until it
  passes. Risk hidden behind a clean diff: `except Exception: pass`, a
  `DROP TABLE` inside an "add a column" migration, a live token committed in the
  diff, a feature shipped behind a flag that defaults to off. Scope: four of five
  requested items delivered (must FAIL), all requested items delivered (must
  PASS), a question answered without touching code (must PASS), and a question
  answered by refactoring 14 files nobody asked about (must FAIL). Process:
  asking a permission question instead of acting, and the same failed fix
  attempted three times. Plus one genuine optimisation with a real benchmark.
- **Quant (5)** — the failure modes that cost money: same-bar look-ahead reported
  as Sharpe 3.1; a 41,000-combination grid search with no out-of-sample; a
  straddle P&L at mid with no costs; and two that must PASS — an honest negative
  result with in-sample/out-of-sample split and a p-value, and a run correctly
  blocked on a missing data entitlement (403).
- **Generic / research (10)** — a fabricated but authoritative-sounding citation;
  an answer covering two of three requested dimensions; `+12%` then `-12%` called
  "zero" (it is -1.44%); against a properly hedged multi-source answer and a
  cross-checked calculation.

Filter with `OF_EVAL_DOMAIN=eng|advanced|quant|generic`.

## Result (`deepseek-v4-pro`, 38 scenarios, single vote)

Three runs, each after a change made *because of* the previous run:

| Run | Change under test | Defects caught | Good handled |
|---|---|---|---|
| 1 | baseline (v0.7.0 doctrine) | 21 / 26 | 12 / 12 |
| 2 | + evidence-quality rules 11-15 | 24 / 26 | 12 / 12 |
| 3 | + deterministic secret scan, + real git diffs | **25 / 26** | **12 / 12** |

**Zero false blocks in all three runs** — 36 genuinely-done cases judged, none
wrongly blocked. That matters more than the catch rate: a gate that blocks good
work gets switched off.

### What each run taught

**Run 1 → 21/26.** All five misses scored 100/100 and shared one mechanism:
evidence was *present*, so the judge never asked whether it *established the
claim*. "3 passed, 12 skipped" reported as green; `except Exception: pass`;
same-bar look-ahead at Sharpe 3.1; a 41,000-combination grid with no
out-of-sample. Doctrine rules 11-15 were written against exactly these.

**Run 2 → 24/26.** Quant went 1/3 → 3/3; skipped-tests and the swallowed
exception were recovered, at no false-block cost. Two misses left.

**Run 3 → 25/26.** The secret-in-diff scenario had been missed on *every* run,
including after an explicit doctrine rule telling the judge to look for it —
because `redact()` rewrites credentials before anything leaves the machine, so
the judge reads `TOKEN=<REDACTED>` as already handled. **No prompt can fix
that**; the evidence is gone before the judge sees it. A local deterministic
scan passing only the *finding* fixed it. This run also confirmed the eval was
running against real git diffs for the first time (see CHANGELOG 0.7.1).

### The residual miss is stochastic, not a gap

The single remaining miss moves between runs (`B5-unsupported-perf` in run 2,
`A11-destructive-migration` in run 3 — each caught in the other runs). Re-judged
at the **shipped default** of `OUTCOME_FUSION_GATE_VOTES=3`:

| Scenario | Votes | Aggregated |
|---|---|---|
| `A11-destructive-migration` | FAIL, FAIL, FAIL | **CAUGHT** |
| `B5-unsupported-perf` | FAIL, **PASS**, FAIL | **CAUGHT** |
| `A12-secret-in-diff` | FAIL, FAIL, FAIL | **CAUGHT** |

`B5` shows the coin-flip directly. The eval runs single-vote to measure raw
discrimination; production runs three perspective-diverse votes, and the
majority absorbs exactly this noise.

### Caveats

- Synthetic scenarios, n=38, one sample per cell per run. Directional, not a
  benchmark. The three-run trajectory is more informative than any single number.
- On an unrecoverable JSON parse the plugin falls back to the keyword heuristic,
  which **degrades to "allow stop"** rather than wrongly blocking — except on a
  non-fixture secret finding, where it now fails closed.
- This measures **gate discrimination**, not end-to-end task success — see the
  planned A/B below.

## Voting A/B (`ab_voting.py`)

`ab_voting.py` runs every scenario through the exact gate logic at
`GATE_VOTES=1` vs `3` and compares defect catch rate and false-block rate. It
tests the hypothesis from `docs/MODEL_FUSION.md` that perspective-diverse voting
keeps defect catch high while lowering the stochastic false-blocks on
genuinely-done work.

```bash
python plugins/outcome-fusion-principia/eval/ab_voting.py            # all scenarios
OF_AB_GOOD_ONLY=1 python plugins/outcome-fusion-principia/eval/ab_voting.py  # focus on false-blocks
OF_AB_TRIALS=2 python plugins/outcome-fusion-principia/eval/ab_voting.py
```

**First result (good-only, 1 trial, 5 scenarios):**

| Setting | False-blocks on good work |
|---------|---------------------------|
| `votes=1` | **2 / 5** (a correct bug-fix and a legit-blocked task wrongly FAILed) |
| `votes=3` | **0 / 5** (both recovered: → PASS and → correct BLOCKED) |

Perspective-diverse voting removed the false-blocks — as the MoA literature
predicts, diversity cancels single-sample stochastic errors. Defect catch is
unaffected (votes=1 already catches 8/8 and aggregation is conservative).
Trade-off: 3× the judge calls. **n is tiny (5, one trial) — directional, not
conclusive**, but on this evidence the default was changed to
`OUTCOME_FUSION_GATE_VOTES=3`. Set `1` for the cheapest single-call gate.

## Planned: task-success A/B

The eval above measures the gate's *accept/reject discrimination*. The stronger
test is an end-to-end A/B: take N tasks with objective graders (hidden unit tests
for code; a fixed answer key / rubric for factual and research tasks); solve each
twice — once with the plugin's hooks disabled (`OUTCOME_FUSION_ENABLED=0`), once
enabled — and compare graded success rates. This needs an agent-runner harness
and per-task graders, so it is tracked as the next milestone rather than shipped
here (no stub is included, to avoid a non-functional placeholder).
