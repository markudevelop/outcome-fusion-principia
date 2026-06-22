# Changelog

## 0.6.0

### Changed
- **Default `OUTCOME_FUSION_GATE_VOTES` is now `3`** (was `1`). The A/B
  (`eval/ab_voting.py`) showed a single judge sample false-blocks genuinely-done
  work (2/5) while 3 perspective-diverse votes did not (0/5). Costs 3× judge
  calls per gate; set `1` for the cheapest single-call gate. (Small-n evidence —
  honestly noted, but it's the better default.)

### Added
- **"Stop stopping" / auto-continue.** On a FAIL the gate now forces Claude to
  keep working **in the same turn** via a Stop-hook `decision: block` (previously
  it only left non-blocking guidance for the next turn, so you had to re-prompt).
  Bounded by `OUTCOME_FUSION_MAX_CONTINUES` and the same-diff guard. Disable with
  `OUTCOME_FUSION_AUTOCONTINUE=0`. New `continue_decision()` helper + 2 tests.

## 0.5.3

### Added
- **Voting A/B harness** (`eval/ab_voting.py`) — runs the scenarios through the
  exact gate at `GATE_VOTES=1` vs `3` (streaming; `OF_AB_GOOD_ONLY`,
  `OF_AB_TRIALS`). First measured result: `votes=3` cut false-blocks on
  genuinely-done work from **2/5 → 0/5** vs `votes=1`, with defect catch
  unaffected — directional support for perspective-diverse voting (small n).
  Recommendation documented: default stays `1`; use `3` for higher-stakes turns.

## 0.5.2

### Fixed
- **Windows hook crash on non-ASCII output.** `json_stdout` printed with the
  process default encoding, so a single non-ASCII char the model echoed (e.g. an
  arrow `↔`) raised `UnicodeEncodeError` on Windows cp1252 stdout and killed the
  Stop hook. It now writes UTF-8 bytes directly with an ASCII-escaped fallback.
  Verified under a simulated cp1252 stdout; covered by a regression test.

## 0.5.1

### Added
- **Integration test suite** (`tests/test_integration.py`) — the "does it all
  work together" check. Verifies manifest ↔ files consistency (every command,
  agent, and skill exists with valid frontmatter), that `hooks.json` only uses
  valid Claude Code events and references existing scripts, that all scripts
  compile, and that the full hook pipeline
  (`compile_prompt` → `capture_tool` → `session_context` → `release_gate`) runs
  end-to-end **offline** (heuristic fallback) producing the right shared
  workspace files, with evidence dedup confirmed. 46 tests total; runs in CI.

## 0.5.0

### Added
- **Model-fusion principles, applied** (see
  [`docs/MODEL_FUSION.md`](plugins/outcome-fusion-principia/docs/MODEL_FUSION.md)).
  Researched the Mixture-of-Agents / LLM-ensemble literature and applied the
  parts that fit a hosted-API plugin:
  - **Perspective-diverse voting.** With `OUTCOME_FUSION_GATE_VOTES>1`, the judge
    samples are no longer identical re-rolls — each gets a distinct lens
    (evidence, completeness, simplicity, correctness). Diversity of independent
    attempts is what the research says drives the gain (incl. the self-MoA
    finding that perspective diversity matters more than vendor diversity).
  - When voting, the **aggregated** review (with the vote breakdown) is written
    to `review.md` for auditability.

  Documented but deliberately not shipped on-by-default: a full MoA aggregator
  pass (extra cost) and weight-merging/knowledge-fusion (impossible vs hosted
  models). Honesty note in the doc: no public evidence ties any specific
  frontier model to this technique; we apply the principles, not a vendor recipe.

## 0.4.1

### Added
- **`/cost` command** + a usage line on session start: totals DeepSeek calls,
  tokens, and latency from `metrics.jsonl` (`summarize_metrics`).

### Fixed
- **Proof-ledger spam.** `capture_tool` no longer appends a duplicate Evidence
  block for a verification command already recorded this session
  (`evidence_already_recorded`).

### Tests
- Expanded to 38 unit tests: markdown-fence + last-object JSON parsing, balanced
  span counting, private-key redaction, transcript-id session keys,
  retry-exhaustion, review aggregation edges, metrics summary, evidence dedup.

## 0.4.0

### Added
- **Universal scope.** The mission compiler and the release gate now explicitly
  handle any task — engineering, research, writing, analysis, factual Q&A,
  planning — and judge with task-appropriate evidence (sources/citations/
  cross-checks for non-code work) instead of demanding a git diff or tests.
  Measured: the eval's `generic` set catches a wrong fact, an unsourced
  overclaim, and an incomplete answer (3/3) while passing good answers (2/2).
- **`research-scientist` skill** and **`evidence-auditor` agent** for non-code
  claims (sourcing, accuracy, completeness, counter-evidence).
- **Self-consistency voting.** `OUTCOME_FUSION_GATE_VOTES > 1` polls the judge N
  times and takes the majority verdict (ties/BLOCKED resolve conservatively),
  reducing run-to-run variance. Default 1.
- **Cost/latency telemetry.** Each DeepSeek call's tokens and latency are written
  to `metrics.jsonl` in the session workspace.
- **Generic eval scenarios + `OF_EVAL_DOMAIN` filter**, and a secret-gated
  `eval` CI workflow. A task-success A/B protocol is documented as the next step.

## 0.3.9

### Fixed
- **Lazy-impossibility false positives.** The detector flagged any occurrence of
  "impossible / cannot / can't / won't work" — including when the agent was
  *quoting* the word, showing it in code, discussing the rule, or listing it in a
  markdown table. That forced spurious release-gate FAILs (observed repeatedly).
  It now strips quoted/code spans and ignores rule-discussion and table-cell
  lines, so it fires only on a genuine prose refusal. Covered by a labelled
  false-positive test set.
- **`memory.md` no longer accumulates duplicates.** `append_memory` skips a
  lesson identical to one already recorded, instead of piling up the same line.

## 0.3.8

### Added
- **`eval/` harness** — a reproducible benchmark of the release gate's
  discrimination: it feeds the shipped gate labelled end-states (genuinely done
  vs. planted release-critical defects) and reports how many defects are caught
  versus the no-plugin baseline of 0. Lives inside the plugin folder at
  `plugins/outcome-fusion-principia/eval/` so it ships with the plugin.

### Improved
- **Judge JSON parsing is now deterministic (root-cause fix).** The eval surfaced
  that the gate intermittently fell back to the keyword heuristic. Inspecting the
  raw replies showed why: reasoning models emit a *thinking preamble before the
  JSON*, and the old greedy `{.*}` regex started at the first brace — sometimes a
  stray brace inside the prose — and failed to parse. `parse_json_loose` now
  brace-counts (string-aware) and returns the last balanced object that parses,
  so the verdict is recovered regardless of preamble. This is the fix that moves
  the number.
- **Belt-and-suspenders retry (`call_deepseek_json`).** On a still-unparseable or
  empty reply the gate re-asks once with a stricter "JSON only" instruction
  before any heuristic fallback (`OUTCOME_FUSION_JSON_RETRIES`, default 1).
- Both paths are covered by deterministic unit tests (reasoning-preamble parsing,
  braces-inside-strings, and retry recovery).

## 0.3.7

### Fixed
- **Release gate never ran.** `release_gate.py` built its DeepSeek prompt with
  `PROMPT.format(...)`, but the prompt embeds a literal JSON schema whose `{ }`
  braces made `str.format` raise `KeyError: '\n  "verdict"'` on every Stop. The
  gate silently fell back to a heuristic in 100% of sessions. Added a
  brace-safe `safe_format()` helper (substitutes only named `{tokens}`) and
  switched the gate to it.
- **Lazy-impossibility detector always fired.** It scanned the recent transcript,
  which includes the plugin's own injected rules ("never say impossible,
  cannot, no edge..."), so the heuristic fallback always took the FAIL branch and
  spammed the same memory line. It now scans only Claude's final message.
- **No retry on transient network.** A single connect timeout degraded the whole
  hook to a fallback. `call_deepseek()` now does one bounded retry
  (`OUTCOME_FUSION_RETRIES`, default 1) on `URLError` / 429 / 5xx, within the
  hook timeout budget.

### Added
- **Visible prompt rewrite.** On `UserPromptSubmit`, the compiled mission is now
  printed to the terminal so you can see exactly how your prompt was rewritten.
  Controlled by `OUTCOME_FUSION_SHOW_MISSION` (default on) and
  `OUTCOME_FUSION_SHOW_MISSION_CHARS` (default 4000). Your original prompt is
  never replaced; the mission is added as context.

### Removed
- **`guard_bash.py`.** It was never wired into `hooks.json` (no `PreToolUse`
  hook) and the plugin already advertises "no Bash guard." Dead code removed to
  cut surface area. `OUTCOME_FUSION_RISK_MODE` is no longer used.

## 0.3.6
- Session isolation and resume. Each Claude Code conversation gets its own
  workspace under `.ai/outcome_fusion/sessions/<session>/`.

## 0.3.5
- Completion closure: a final gap audit before the release gate returns PASS.
