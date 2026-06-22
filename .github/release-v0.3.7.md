# Outcome Fusion Principia v0.3.7

**Model fusion for Claude Code: one model builds, a different model judges.**

Claude does the building; DeepSeek independently judges the mission, the git
diff, the tool log, and a proof ledger, returning PASS / FAIL / BLOCKED so your
agent can't grade its own homework or quit early.

## Highlights
- 🧠 **Visible prompt rewrite** — your prompt is compiled into a precise,
  testable mission and shown in your terminal (your original prompt is never
  replaced).
- ⚖️ **Working release gate** — the cross-model judge now actually runs. It
  previously crashed on an unescaped-brace `str.format` bug and silently fell
  back to a heuristic in *every* session.
- 🚫 **Impossibility breaker** — lazy "can't be done" is met with a demand for
  proof or a falsification test.
- ✅ **Tests + CI** — 16 unit tests including regression locks for the two fixed
  bugs; GitHub Actions runs them on every push.
- 🧹 Removed the unused `guard_bash.py` and `OUTCOME_FUSION_RISK_MODE`.

## Install
```
/plugin marketplace add markudevelop/outcome-fusion-principia
/plugin install outcome-fusion-principia@outcome-fusion-local
```

Set `DEEPSEEK_API_KEY` (or an Anthropic-compatible `ANTHROPIC_API_KEY`). Without
a key, the plugin degrades gracefully to a built-in heuristic — it never blocks
your session.

Full changelog: [`CHANGELOG.md`](../CHANGELOG.md)

---

## Repo metadata (for `gh repo edit` / GitHub UI)

**Description:**
> Model fusion for Claude Code — one model builds, a second model (DeepSeek) judges the results. First-principles missions, a proof ledger, and a release gate that won't let your agent stop early.

**Topics:**
`claude-code` `claude-code-plugin` `llm` `agents` `agentic-ai` `deepseek`
`model-fusion` `llm-as-judge` `developer-tools` `verification` `hooks` `mit`

**One-paste publish (after `gh auth refresh -h github.com -s repo`):**
```bash
cd ~/Downloads/outcome_fusion_principia_operator_v3_6_session_resume
gh repo create outcome-fusion-principia --public --source=. --remote=origin --push
gh repo edit --description "Model fusion for Claude Code — one model builds, a second model (DeepSeek) judges the results." \
  --add-topic claude-code --add-topic claude-code-plugin --add-topic llm --add-topic agents \
  --add-topic agentic-ai --add-topic deepseek --add-topic model-fusion --add-topic llm-as-judge \
  --add-topic developer-tools --add-topic verification --add-topic hooks
git tag v0.3.7 && git push origin v0.3.7
gh release create v0.3.7 --title "v0.3.7 — Model fusion judge" --notes-file .github/release-v0.3.7.md
```
