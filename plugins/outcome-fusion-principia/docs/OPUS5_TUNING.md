# Tuning Outcome Fusion for Claude Opus 5 (v0.7.0)

Two things changed under this plugin at once: Claude Opus 5 shipped, and Anthropic
cut Claude Code's own system prompt by ~80%. Both change what a harness like this
should do. v0.7.0 is the adjustment.

## The conflict, and how it was resolved

Two sources drove this release and they disagree in one place.

**Anthropic, [Prompting Claude Opus 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)** —
Opus 5 verifies its own work without being told, expands task scope on its own
judgment, narrates more, and delegates to subagents more readily. Its explicit
instruction:

> If your prompt contains explicit verification instructions ("include a final
> verification step for any non-trivial task," "use a subagent to verify"), remove
> them: instructions like these cause over-verification on Claude Opus 5, and
> removing them reduces wasted tokens with no loss in quality. **The same applies
> to legacy harness scaffolding that adds separate verification steps.**

That last sentence describes this plugin.

**productcompass.pm, "How to Heal Claude Opus 5"** — add three blocks to
CLAUDE.md: *Act, don't ask*; *A question is a question*; *Done means done*.

The resolution v0.7.0 uses:

> Verification is kept **only where it is out of band**. A different model (the
> DeepSeek release gate) judging Claude's finished work after the fact is not
> "over-verification" — it is an independent check Claude cannot do for itself.
> What was removed is every instruction telling **Claude** to re-check itself,
> because that is the thing that now compounds with its own behaviour and costs
> tokens for nothing.

All three productcompass blocks are adopted. "A question is a question" turned out
to be the highest-value one, because this plugin was actively violating it.

## What changed

### 1. Intent router — a question is a question

Before v0.7.0, **every** prompt was compiled into a full "execute this release
ready" mission and then judged by a 3-vote release gate that could force Claude to
keep working. Asking *"what does the gate do?"* produced a mission, a verification
plan, release criteria, and a gate that could block the answer as incomplete.

Now `classify_intent()` (in `scripts/common.py`) splits prompts locally, for free:

| Intent | Mission compiled | Release gate | Injected context |
|---|---|---|---|
| `build` | yes | yes | mission + Opus 5 operating block |
| `question` | no | **off for that turn** | answer-only instruction + operating block |

The classifier is deliberately biased toward `build`. A build prompt misread as a
question just loses the mission (soft failure); a question misread as a build
triggers implementation nobody asked for (the failure being removed).

Rules, in order: `build:`/`do:`/`task:` and `q:`/`ask:`/`question:` prefixes win;
then any build verb, want/directive phrase, or defect vocabulary anywhere in the
prompt means build; then an interrogative opener or a trailing `?` means question;
otherwise build.

**Calibration is measured, not guessed.** 474 real prompts from this project's
transcripts were replayed through the classifier and every question-mode
classification was audited by hand. Three rounds of fixes came out of that audit:

- bare `do X` is an order (`do it all`, `do 2% for her`) while `do you/we/...` is a question;
- want/directive phrases are orders (`i need this on the website`, `ok lets use the new one`, `all of this should be commited`);
- defect vocabulary is an order (`again it seems we had an issue with the publisher?` wants a fix, not an essay).

Final split: **14.1% question / 85.9% build**, with the remaining question set
manually confirmed as genuine questions.

`OUTCOME_FUSION_INTENT_ROUTER=0` restores pre-0.7.0 behaviour (everything is a build).

### 2. Self-recheck instructions removed

- The injected core rules dropped rule 8 ("before final answer, run the internal
  closure question…"). The closure audit still runs — in the gate, out of band.
- The mission template's "Verification plan" section became "Evidence that
  counts", and explicitly tells the compiler not to request a separate final
  verification pass or a verification subagent.
- `skills/principia/SKILL.md` gained a scope-and-cost section saying the same.
- `agents/verification-scientist.md`'s description now says *do not* invoke it to
  routinely double-check your own work; the other four agents' descriptions were
  narrowed so they stop auto-triggering on routine tasks.

A test (`test_no_self_recheck_instructions_are_injected`) fails the build if a
"double-check" / "re-verify" / "final verification step" instruction reappears in
anything the plugin injects, unless it is inside a "do not" clause.

### 3. Opus 5 operating block

`common.OPUS5_OPERATING_BLOCK` is injected on every turn (both modes) and covers
each behaviour Anthropic flags as needing tuning: scope discipline, done-means-done
completion, act-don't-ask, narration cadence, correction narration, written
deliverable length, subagent delegation caps, and no stacked self-verification.

### 4. The gate stops expanding scope

Opus 5 widens scope on its own; a judge that also invents scope and then *forces
continuation* is the worst version of that. The gate doctrine gained two rules:

- judge against the mission's scope; unrequested improvements are
  `non_blocking_followups` and must never cause a FAIL;
- do not FAIL for the absence of a separate verification pass — the gate *is* that pass.

The mission template gained a `# Scope lock` section naming what is explicitly out
of scope.

### 5. Cost

Measured on this project's own telemetry (2,703 DeepSeek calls, 51.9M input tokens
across 184 sessions):

| Change | Measured effect |
|---|---|
| Intent router | 381 of 2,703 calls (14.1%) and 7.3M input tokens never happen |
| Gate payload caps | proof + tool_log payload 54.4% smaller across 181 real sessions |
| Transcript cap 50k → 20k chars | applies to every vote of every gate call |
| Diff cap 100k → 40k chars | ditto |
| Compile effort `high` → `medium` | 724 calls per this project's history |

The gate ran **2.73 calls per compiled turn** (3 votes × autocontinue rounds), so
every byte in its prompt is paid for roughly three times.

Every cap is an env var; set them back to the old values to revert.

## Environment variables added in 0.7.0

| Variable | Default | Purpose |
|---|---|---|
| `OUTCOME_FUSION_INTENT_ROUTER` | `1` | Question/build routing. `0` = pre-0.7.0 behaviour |
| `OUTCOME_FUSION_COMPILE_EFFORT` | `medium` | Effort for mission compilation only |
| `OUTCOME_FUSION_MAX_DIFF_CHARS` | `40000` | Git diff sent to the gate (was 100000) |
| `OUTCOME_FUSION_MAX_TRANSCRIPT_CHARS` | `20000` | Transcript tail sent to the gate (was 50000) |
| `OUTCOME_FUSION_MAX_PROOF_CHARS` | `30000` | Proof ledger tail sent to the gate (was 50000) |
| `OUTCOME_FUSION_MAX_TOOLLOG_CHARS` | `12000` | Tool log tail sent to the gate (was 50000) |

## Known limits

- The classifier is lexical, not semantic. It is calibrated on one user's 474
  prompts in one repo; a different working style will need different verbs. The
  bias toward `build` means miscalibration degrades gracefully.
- The payload caps are a cost change with an **unmeasured** quality effect. The
  judge sees less context; no A/B has been run on whether verdict quality holds.
  `eval/ab_voting.py` is the harness to run it with.
- Effort is passed as `output_config.effort`; whether the configured endpoint
  honours it is provider-dependent and unverified here.
