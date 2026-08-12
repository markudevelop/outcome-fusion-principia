# Changelog

## 0.7.0 — tuned for Claude Opus 5

Driven by Anthropic's [Prompting Claude Opus 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)
guide and productcompass.pm's "How to Heal Claude Opus 5". They conflict on
verification; the resolution and the measurements are in
[`docs/OPERATING_DOCTRINE.md`](plugins/outcome-fusion-principia/docs/OPERATING_DOCTRINE.md).

### Added
- **Intent router — a question is a question.** `classify_intent()` splits every
  prompt locally into `build` or `question`. A question gets an answer-only
  instruction, **no compiled mission, and no release gate for that turn**;
  previously *every* prompt — including "what does this do?" — produced a full
  release mission and a 3-vote gate that could force Claude to keep working.
  Calibrated by replaying **474 real prompts** and hand-auditing every question
  classification: bare `do X` is an order but `do you/we ...` is a question,
  want/directive phrases (`i need this on the website`) are orders, and defect
  vocabulary (`we had an issue with the publisher?`) is an order. Final split
  14.1% question / 85.9% build. Biased toward `build` by design. Disable with
  `OUTCOME_FUSION_INTENT_ROUTER=0`; force per-prompt with a `build:` / `q:` prefix.
- **Opus 5 operating block** injected on every turn: scope discipline,
  done-means-done, act-don't-ask, narration cadence, correction narration,
  deliverable length, and a subagent delegation cap.
- **`# Scope lock`** section in the compiled mission naming what is out of scope.
- `docs/OPERATING_DOCTRINE.md`, and 65 new tests (`tests/test_opus5_tuning.py`).

### Changed
- **Removed the self-recheck instructions Anthropic says to remove.** Injected
  rule 8 ("before final answer, run the internal closure question...") is gone;
  the mission template's "Verification plan" is now "Evidence that counts" and
  explicitly forbids asking for a separate final verification pass or a
  verification subagent. The closure audit still runs — in the gate, out of band.
  A test fails the build if such an instruction reappears anywhere the plugin
  injects. Out-of-band verification (a different model judging after the fact) is
  kept in full; only "Claude, check yourself again" was removed.
- **Agent descriptions narrowed** so they stop auto-triggering on routine work.
  `verification-scientist` now says explicitly not to invoke it to double-check
  your own work.
- **Gate doctrine no longer expands scope**: unrequested improvements are
  `non_blocking_followups` and must never cause a FAIL, and the gate may not FAIL
  for the absence of a separate verification pass.
- **Gate payload budget**, all env-tunable: diff 100k→40k, transcript 50k→20k,
  proof 50k→30k, tool log 50k→12k chars. Measured across 181 real sessions the
  proof+tool_log payload is **54.4% smaller**; the gate ran 2.73 calls per
  compiled turn, so every byte was paid for ~3×.
- **Per-call effort.** Mission compilation drops to `medium`
  (`OUTCOME_FUSION_COMPILE_EFFORT`); the gate stays `high`.

- **Done means done, checked mechanically.** The compiled mission carries a
  `# Deliverables checklist` (one line per discrete thing the user asked for) and
  the gate returns a `deliverables_status` entry per item (`done`/`partial`/
  `missing` + evidence or a named blocker). Any non-`done` item without a proven
  blocker is a FAIL; the terminal line reads `Delivered: 3/5 requested items` and
  names what is outstanding.
- **The gate now sees the verbatim user request** (`request.txt`), not only the
  compiled mission, with an explicit tie-break: if the mission disagrees with the
  request, the request wins. Previously a compiler that drifted from the user's
  intent produced a gate that faithfully enforced the drift.
- **Eval suite expanded 13 -> 38 scenarios** across four domains (eng, advanced,
  quant, generic), built so a keyword-matching judge gets them wrong: vacuous
  tests, `3 passed, 12 skipped` reported as green, a test asserting the bug, a
  flaky rerun-until-green, `except Exception: pass`, a `DROP TABLE` inside an
  "add a column" migration, a committed live token, a feature behind an off flag,
  same-bar look-ahead at Sharpe 3.1, a 41k-combination grid with no OOS, a
  fabricated citation, and +12%/-12% called "zero". Plus must-PASS cases: an
  honest negative result with IS/OOS and a p-value, a legitimately blocked run,
  a question answered without touching code, and a real benchmark.

### Fixed
- **Credential routing (security-relevant).** `get_base_url()` fell back to
  `ANTHROPIC_BASE_URL`, which is set in ordinary environments (Claude Code,
  gateways, proxies) — so a user with `DEEPSEEK_API_KEY` had that key posted as
  `x-api-key` to Anthropic's host. Every call 401s, the gate silently degrades to
  the keyword heuristic permanently, and a credential leaves for a host it was
  never issued for. `ANTHROPIC_BASE_URL` is now honoured only for an Anthropic
  key. Found by running the eval, which returned 13/13 HTTP 401.

### Judge model
Measured head-to-head on the 13-scenario eval: `deepseek-v4-pro` 8/8 defects and
5/5 good; `deepseek-v4-flash` 8/8 defects but 4/5 good — it false-blocked the
legitimately-blocked scenario, which in this plugin triggers auto-continuation on
a task that genuinely needs an external credential. **Pro stays the default.**
Flash is ~3.1x cheaper and both aggregate to the correct verdict at
`GATE_VOTES=3`, so `OUTCOME_FUSION_MODEL=deepseek-v4-flash` is a supported
cost-first choice. n=13, single samples: directional, not conclusive.

### Note on naming
The operating block is **model agnostic**: injected on every turn whatever model
drives the session, with no model name in anything the agent or judge reads (a
test enforces this). `OPUS5_OPERATING_BLOCK` -> `AGENT_OPERATING_BLOCK`,
`docs/OPUS5_TUNING.md` -> `docs/OPERATING_DOCTRINE.md`. The Opus 5 guidance is
where the rules came from, not a restriction on where they apply.

- **Two quant skills shipped**: `bucket-brute-force` (the default edge-discovery
  method — sweep the full honest event set by decision-time-knowable dimensions,
  keep only buckets paying in both halves; lag manifest required, lift-t with a
  date-clustered SE against an empirical null) and `quant-aggregation-integrity`
  (audit from the lowest available unit and aggregate only after every nonlinear
  transformation and cost). `quant-scientist` now routes to both. Ported from
  local skills with all private repo paths, strategy names and dated P&L
  references stripped; a test asserts no shipped skill contains a private marker.
- **Gate doctrine rules 12-14: evidence QUALITY, not evidence presence.** The
  first 38-scenario run caught 21/26 with zero false blocks, and all five misses
  scored 100/100 with the same root cause — evidence was present, so the judge
  never asked whether it established the claim. Added: defective test evidence
  (skipped/deselected tests, assertions that prove nothing, rerun-until-green,
  off-by-default flags), danger in the diff read independently of the claim
  (credential literals, destructive ops, swallowed exceptions, removed checks),
  and quant method defects (look-ahead, no OOS, omitted costs, survivorship,
  missing n). The evidence voting lens was sharpened from "is every claim
  verified?" (a presence question that passed all five) to "what did the test or
  source NOT cover?"

### Removed
- Dead read of `memory.md` in the release gate — it was loaded on every gate call
  and never sent to the judge.

### Measured
On this project's own telemetry (2,703 DeepSeek calls / 51.9M input tokens across
184 sessions), the intent router alone removes **381 calls (14.1%) and 7.3M input
tokens**. The payload caps are a cost change with an unmeasured quality effect —
`eval/ab_voting.py` is the harness to test it.

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
