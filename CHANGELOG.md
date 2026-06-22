# Changelog

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
