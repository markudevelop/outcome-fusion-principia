# Changelog

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
