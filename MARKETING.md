# Outcome Fusion Principia — launch copy

**Core concept: model fusion.** One model *builds* (Claude Code). A second,
independent model *judges* the result (DeepSeek). The builder is graded by a
different mind than the one that wrote the code — so it can't rubber-stamp its
own work. Cross-model judging is what lifts the output: missions get sharper,
claims get verified, and the agent doesn't get to quit early.

> One model builds. Another model judges. The result is better than either alone.

---

## Taglines

- **Two models are better than one.** A builder model and a judge model, fused.
- **Your agent just got a second opinion — from a different model.**
- **Model fusion for coding agents: one builds, one judges, results improve.**
- **The judge model that won't let your agent stop at "good enough."**

---

## X / Twitter thread

**1/**
Single-model agents grade their own homework.

So I built Outcome Fusion Principia: a Claude Code plugin where a *second*
model (DeepSeek) judges every result.

One model builds. A different model judges. Open source, MIT 👇

**2/**
The idea is model fusion.

Claude writes the code. DeepSeek independently reviews the mission, the git
diff, the tool log, and the proof — then returns PASS / FAIL / BLOCKED.

A different mind catches what the builder rationalizes away.

**3/**
It runs on 3 hooks, zero workflow change:

• You type a prompt → DeepSeek rewrites it into a precise mission (shown in your
  terminal — your prompt is never replaced)
• Claude works → every test/lint/build is logged to a proof ledger
• Claude tries to stop → the judge model decides if it's actually done

**4/**
My favorite part: the impossibility breaker.

If the agent says "this is impossible / can't be done," the judge demands proof
or a falsification test. No lazy refusals. No fake "done."

**5/**
Brutal honesty: when I open-sourced it I found the judge had been silently
crashing on a one-line bug in *every* session.

Fixed it, then wrote 16 regression tests so it can never happen again. CI green. ✅

**6/**
MIT licensed. Install straight from GitHub in Claude Code:

/plugin marketplace add markudevelop/outcome-fusion-principia
/plugin install outcome-fusion-principia@outcome-fusion-local

⭐ github.com/markudevelop/outcome-fusion-principia

---

## LinkedIn

**Model fusion: one model builds, another judges — and the agent gets better.**

Coding agents have a blind spot: the same model that writes the solution also
decides when it's finished. It grades its own homework.

Outcome Fusion Principia is an open-source Claude Code plugin that fixes that by
fusing two models into one loop:

→ Claude builds.
→ DeepSeek judges — independently reviewing the mission, the diff, the tool log,
   and the evidence, then returning PASS / FAIL / BLOCKED.

Because the judge is a *different* model, it catches the things a single model
talks itself past: unverified claims, "good enough" stops, and lazy
"impossible" refusals (which it answers with "prove it or run a falsification
test").

It runs entirely through Claude Code hooks — no workflow change:
• Your prompt is rewritten into a precise, testable mission (and shown to you).
• Every test/lint/build is recorded in a per-session proof ledger.
• A release gate blocks "done" until the work is actually verified.

It's MIT licensed, has a passing test suite, and installs from GitHub in two
lines. If you build with agents, I'd love your feedback.

#AI #LLM #DeveloperTools #OpenSource #ClaudeCode #AgenticAI

---

## Show HN / Reddit (r/LocalLLaMA, r/ClaudeAI)

**Show HN: Model fusion for coding agents — a second model judges the first**

Outcome Fusion Principia is an open-source (MIT) Claude Code plugin built on one
idea: don't let a single model grade its own work.

Claude does the building. A different model — DeepSeek — acts as the judge. On
every attempt to finish, the judge independently reviews the mission, the git
diff, the transcript, the tool log, and a proof ledger, and returns
PASS / FAIL / BLOCKED. If the work is weak or a claim is unverified, the agent
is pushed to continue with concrete next steps instead of stopping.

Three hooks, no workflow change:
- UserPromptSubmit → rewrites your prompt into a precise mission (shown in the
  terminal; your prompt is never replaced)
- PostToolUse → logs commands and records verification evidence
- Stop → the cross-model release gate

It also has an "impossibility breaker" (lazy "can't be done" gets met with a
demand for proof or a falsification test) and a completion-closure audit (it
runs the "anything else?" check before declaring done).

Honest origin story: I only discovered the judge had been crashing on an
unescaped-brace bug in *every* session once I started prepping it for release.
Fixed, plus 16 regression tests and CI so it stays fixed.

Repo + README: github.com/markudevelop/outcome-fusion-principia
Feedback and PRs welcome.
