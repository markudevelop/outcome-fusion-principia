#!/usr/bin/env python3
from __future__ import annotations

from common import (
    call_deepseek,
    cwd_from_hook,
    default_mission,
    env_bool,
    env_int,
    json_stdout,
    project_signals,
    combined_memory,
    mirror_latest,
    read_stdin_json,
    safe_read,
    safe_write,
    should_skip_prompt,
    session_paths_block,
    workspace_dir,
)

SYSTEM = """
You are Outcome Fusion Principia, a first principles mission compiler for Claude Code.
Your job is to turn the user's rough prompt into a precise scientific mission Claude can execute without babysitting.
Do not rewrite the user's intent. Do not add fake scope. Do not lower ambition.
Use first principles, falsification, simplification, evidence, and release readiness.
The user wants autonomous progress, not low value clarification questions.
Do not ask the user low value questions. Make reversible assumptions, execute, verify, and report. Only stop for true blockers that cannot be resolved inside the local repo.
You are allowed to be imaginative, but every imaginative path must connect to a test, inspection, calculation, backtest, source, or proof.
Return clean Markdown only.
""".strip()

TEMPLATE = """
User prompt:
{prompt}

Previous mission if any:
{previous_mission}

Project memory:
{memory}

Project signals:
{signals}

Compile a mission using exactly this structure:

# Mission
One direct paragraph describing the result to achieve.

# First principles decomposition
List:
1. Real objective
2. Fundamental constraints
3. Known facts
4. Unknowns that can be checked
5. Parts likely not needed

# Simplification mandate
List what should be removed, avoided, or not built unless evidence proves it is needed.

# Assumptions to proceed
List assumptions Claude should make so it can continue without bothering the user. Each assumption must be reversible or low risk.

# Hard boundaries
List hard limits only when the work truly leaves the local repo or requires credentials, live money movement, legal/compliance authority, or external communication. For normal engineering decisions, make the best assumption and continue.

# Impossibility breaker
State the rule: impossible, cannot, not realistic, no edge, or won't work is not accepted unless verified or reduced to a specific blocker. If the ambitious goal looks unlikely, create experiments instead of refusing.

# Hypothesis map
List 4 to 8 paths. Include obvious paths and at least two non obvious paths. Each path must include what would prove it right or wrong.

# Verification plan
List exact checks Claude should run or inspect. Include build, tests, lint, logs, docs, repo search, calculations, or backtests where relevant.

# Proof ledger requirements
Tell Claude to update the session proof ledger path supplied in the injected context with claim, evidence, method, result, confidence, and remaining risk. Do not use a global proof file.

# Release criteria
Concrete criteria for being done. No fake implementation. No placeholder TODO. No broken imports. No silent failures. Main flow works. Claims are verified or marked uncertain. Before saying done, perform a final "anything else?" audit. If that audit would reveal release critical missed work, fix it before final response. Separate optional future ideas from release blockers.

# Final response format
Only include: done, verified, failed, uncertain, optional non-blocking followups.
""".strip()


def is_anything_else_query(prompt: str) -> bool:
    p = (prompt or "").strip().lower()
    phrases = [
        "anything else", "what else", "did you miss", "missed anything",
        "is there more", "any more", "double check", "final check",
        "are we done", "is it done", "what did you miss"
    ]
    return any(x in p for x in phrases)


def main() -> int:
    payload = read_stdin_json()
    if not env_bool("OUTCOME_FUSION_ENABLED", True):
        return 0
    prompt = payload.get("prompt", "")
    if should_skip_prompt(prompt):
        return 0

    cwd = cwd_from_hook(payload)
    wdir = workspace_dir(cwd, payload)

    if is_anything_else_query(prompt):
        closure = safe_read(wdir / "closure.md", limit=30000)
        review = safe_read(wdir / "review.md", limit=30000)
        proof = safe_read(wdir / "proof.md", limit=30000)
        context = f"""
Outcome Fusion Completion Closure mode is active.
The user is asking whether anything else was missed.
Do not invent new scope, do not create vague nice-to-haves, and do not suddenly discover obvious release-critical work unless you have evidence from files, tests, logs, review, or proof.

Use this rule:
1. If closure says PASS and release_critical_missed_work is empty, answer directly that there is no evidence of release-critical missed work.
2. Report only verified open risks or non-blocking followups already recorded.
3. If you find a real release-critical miss, say it clearly and continue fixing it now.
4. Never save obvious missed work for "anything else?". That work should have failed the previous release gate.

CLOSURE:
{closure}

LAST REVIEW:
{review}

PROOF LEDGER:
{proof}
""".strip()
        json_stdout({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context,
                "sessionTitle": "Outcome Fusion Closure Check"
            },
            "systemMessage": "Outcome Fusion: closure check active. Answer from verified closure state, not fresh speculation.",
            "suppressOutput": True
        })
        return 0

    previous = safe_read(wdir / "mission.md", limit=20000)
    memory = combined_memory(wdir, limit=30000)
    signals = project_signals(cwd)

    try:
        mission = call_deepseek(
            SYSTEM,
            TEMPLATE.format(prompt=prompt, previous_mission=previous, memory=memory, signals=signals),
            max_tokens=5200,
            temperature=0.2,
            timeout=110,
        )
    except Exception as e:
        mission = default_mission(prompt, cwd)
        safe_write(wdir / "last_error.txt", f"compile_prompt fallback: {e}\n")

    safe_write(wdir / "mission.md", mission)
    mirror_latest(wdir, "mission.md", mission)
    if not (wdir / "proof.md").exists():
        safe_write(wdir / "proof.md", "# Proof ledger\n\nRecord every important claim as: claim, evidence, method, result, confidence, remaining risk.\n")
    mirror_latest(wdir, "proof.md")

    context = f"""
Outcome Fusion Principia compiled the user's prompt into a mission.
{session_paths_block(wdir)}

Read and obey the session mission file.
Maintain proof only in the session proof ledger.

Core operating rules:
1. Use first principles and remove non essential parts before adding complexity.
2. Do not ask low value questions. Make reversible assumptions, execute, verify, and report.
3. Do not say impossible, cannot, not realistic, or no edge unless verified or reduced to a specific blocker.
4. Never guess when you can inspect, search, run, calculate, test, backtest, or verify.
5. Be creative, but evidence locked.
6. Final answer must use the mission's final response format.
7. Use the session workspace files above. Do not write global `.ai/outcome_fusion/mission.md`, `proof.md`, or `review.md`.
8. Before final answer, run the internal closure question: “if the user asks anything else, what release critical miss would I admit?” If the answer is non-empty, fix it now.
""".strip()

    terminal_log = env_bool("OUTCOME_FUSION_TERMINAL_LOG", True)
    show_mission = env_bool("OUTCOME_FUSION_SHOW_MISSION", True)
    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
            "sessionTitle": "Outcome Fusion Mission"
        },
        "suppressOutput": True
    }
    if terminal_log:
        if show_mission:
            cap = env_int("OUTCOME_FUSION_SHOW_MISSION_CHARS", 4000)
            body = mission.strip()
            if len(body) > cap:
                body = body[:cap].rstrip() + f"\n... [truncated — full mission: {wdir / 'mission.md'}]"
            out["systemMessage"] = (
                f"Outcome Fusion rewrote your prompt into this mission (session {wdir.name}):\n\n"
                f"{body}\n\n"
                "[Your original prompt is unchanged; this mission is added as context. "
                "Set OUTCOME_FUSION_SHOW_MISSION=0 to hide.]"
            )
        else:
            out["systemMessage"] = f"Outcome Fusion: mission compiled for session {wdir.name}."
    json_stdout(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
