# Security & privacy

This plugin sends context to an external model (DeepSeek, or whatever
`DEEPSEEK_ANTHROPIC_BASE_URL` points at) to compile missions and judge your
work. Be aware of what leaves your machine.

## What is sent to the model

- **Mission compile** (`UserPromptSubmit`): your prompt, the previous mission,
  project memory, and lightweight project signals (file names, scripts).
- **Release gate** (`Stop`): the mission, the **git diff**, a slice of the
  **recent transcript**, the tool log, the proof ledger, and Claude's final
  message.

Nothing is sent on tool-capture or session-start events — those only write local
files.

## Secret redaction

Everything sent is passed through `redact()` first, which masks common secret
shapes: `api_key`/`secret`/`token`/`password`/`private_key`/`bearer` assignments,
`Authorization: Bearer …`, `sk-…`, `ghp_…`, and PEM private-key blocks. Redaction
is pattern-based, so **it is best-effort, not a guarantee** — a secret in an
unusual format can slip through.

If your working tree contains secrets in tracked files, the git diff of those
files could be sent. Review `redact()` (in `scripts/common.py`) and extend the
patterns for your environment, or disable the plugin on sensitive repos.

## Turning it off

- `OUTCOME_FUSION_ENABLED=0` disables every hook.
- Put `nofusion` anywhere in a prompt to skip the compiler for that turn.
- No `DEEPSEEK_API_KEY` (or compatible key) → the plugin runs on a local
  heuristic and makes **no network calls**.

## Local data

Session state lives under `.ai/outcome_fusion/` in your repo (mission, proof,
review, closure, tool log, metrics). Tool logs and proof entries are redacted on
write. Add `.ai/outcome_fusion/` to `.gitignore` (the project template does) so
it is not committed.

## Reporting a vulnerability

Open a GitHub issue, or for sensitive reports contact the maintainer privately
via the repository profile. Please do not include secrets in the report.
