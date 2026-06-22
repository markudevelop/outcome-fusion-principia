#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from common import (
    aggregate_reviews,
    append_memory,
    call_deepseek_json,
    contains_lazy_impossible,
    continue_decision,
    cwd_from_hook,
    env_bool,
    env_int,
    git_status_and_diff,
    json_stdout,
    load_state,
    log_metric,
    make_state_path,
    project_signals,
    vote_lenses,
    read_stdin_json,
    recent_transcript_text,
    safe_format,
    safe_read,
    safe_write,
    save_state,
    mirror_latest,
    session_paths_block,
    workspace_dir,
)

SYSTEM = """
You are Outcome Fusion Principia, a scientific release gate for Claude Code.
You protect the user's ambition, truth, creativity, and release readiness.
You must not be polite if the work is weak.

Doctrine:
1. First principles: reduce the problem to facts, constraints, and testable unknowns.
2. Subtractive design: remove unnecessary steps, code, abstractions, assumptions, and surface area.
3. Scientific method: every important claim needs evidence, a calculation, a source, a test, an inspection, or a falsification plan.
4. Impossible breaker: impossible, cannot, not realistic, no edge, and won't work are lazy unless verified or reduced to a specific blocker.
5. Creative but evidence locked: reward non obvious paths only when tied to experiments.
6. Release ready beats chat ready.
7. If the same failed path repeats, require a different strategy.
8. Completion closure: before PASS, run the exact audit the user would trigger by asking “is there anything else?” If that audit would reveal release critical missed work, verdict must be FAIL now. Do not save missed work for later.
9. Universal scope: the task may be engineering, research, writing, analysis, factual question answering, planning, or decision support. Apply the SAME standard with task-appropriate evidence. For code: build, tests, runs, inspection. For research or factual claims: sources, citations, calculations, cross-checks, and self-consistency. For writing or analysis: does it actually meet the stated requirement, is it accurate, is it complete. NEVER demand code, tests, or a git diff for a task that is not about code; judge it on the evidence that fits its kind. An unsupported factual claim, a missing citation, or an unmet requirement is just as much a FAIL as untested code.

Return compact valid JSON only.
""".strip()

PROMPT = """
MISSION:
{mission}

CLAUDE FINAL MESSAGE:
{last_message}

RECENT TRANSCRIPT:
{transcript}

PROJECT SIGNALS:
{signals}

GIT STATUS:
{git_status}

GIT DIFF HASH:
{diff_hash}

GIT DIFF:
{git_diff}

PROOF LEDGER:
{proof}

TOOL LOG:
{tool_log}

LOOP STATE:
{loop_state}

LAZY IMPOSSIBILITY LANGUAGE DETECTED:
{lazy_impossible}

Judge if Claude is allowed to stop.

Return JSON exactly with these keys:
{
  "verdict": "PASS" or "FAIL" or "BLOCKED",
  "release_ready": true or false,
  "progress_score": 0 to 100,
  "single_blocker": "one sentence",
  "verified": ["evidence actually checked"],
  "unsupported_claims": ["claims still not proven"],
  "simplify_or_remove": ["parts to remove before adding more"],
  "non_obvious_paths": ["creative paths worth testing"],
  "falsification_tests": ["tests or checks that would prove/disprove the path"],
  "next_actions": ["exact next actions for Claude"],
  "closure_audit": {
    "if_user_asks_anything_else": "answer Claude should be able to give after PASS",
    "release_critical_missed_work": ["misses that must be fixed before PASS"],
    "non_blocking_followups": ["optional improvements that are not part of done"],
    "done_lock_reason": "why the work can be considered closed"
  },
  "stop_reason_if_pass": "why stopping is justified",
  "memory_update": "short reusable lesson, empty string if none"
}

Rules:
PASS only if the mission is genuinely done or the remaining blocker is proven and specific. Before PASS, perform a final gap audit: ask internally “if the user asks is there anything else, would I reveal missed release critical work?” If yes, FAIL now and put it in next_actions.
BLOCKED only if continuing truly requires something outside the local repo, such as missing credentials, live money movement, legal authority, external communication, or production access. Do not block for ordinary engineering choices.
FAIL if Claude guessed, refused too early, did not verify, created complexity without need, left release risk, did not update proof, repeated the same failed fix, ignored a viable experiment, or would later discover obvious missed work when asked “anything else?”. Optional nice-to-have improvements are allowed only if clearly labeled non_blocking_followups.
""".strip()


def fallback_review(mission: str, proof: str, tool_log: str, lazy: bool) -> dict:
    if lazy:
        return {
            "verdict": "FAIL",
            "release_ready": False,
            "progress_score": 30,
            "single_blocker": "Lazy impossibility language was used without enough proof.",
            "verified": [],
            "unsupported_claims": ["Impossibility or low feasibility claim needs verification."],
            "simplify_or_remove": ["Remove vague refusal. Replace it with exact blocker or experiment."],
            "non_obvious_paths": ["Try a smaller capacity version, different timeframe, different data split, or reduced scope experiment."],
            "falsification_tests": ["Run the smallest check that could prove or disprove the claim."],
            "next_actions": ["Define what would need to be true, inspect evidence, run one test, then update proof.md."],
            "stop_reason_if_pass": "",
            "memory_update": "Do not accept impossible claims without evidence."
        }
    if mission and not proof.strip():
        return {
            "verdict": "FAIL",
            "release_ready": False,
            "progress_score": 35,
            "single_blocker": "No proof ledger entries exist for the mission.",
            "verified": [],
            "unsupported_claims": ["Completion was not tied to evidence."],
            "simplify_or_remove": [],
            "non_obvious_paths": [],
            "falsification_tests": ["Run or document relevant checks."],
            "next_actions": ["Update proof.md with claims, evidence, method, result, confidence, and remaining risk."],
            "stop_reason_if_pass": "",
            "memory_update": "Always maintain a proof ledger before final completion."
        }
    return {"verdict": "PASS", "release_ready": True, "progress_score": 70, "single_blocker": "", "verified": [], "unsupported_claims": [], "simplify_or_remove": [], "non_obvious_paths": [], "falsification_tests": [], "next_actions": [], "closure_audit": {"if_user_asks_anything_else": "No DeepSeek key; no additional release critical audit available.", "release_critical_missed_work": [], "non_blocking_followups": [], "done_lock_reason": "Heuristic gate allowed stop."}, "stop_reason_if_pass": "No DeepSeek key, heuristic gate allowed stop.", "memory_update": ""}


def compact_list(items, limit=3):
    if not isinstance(items, list):
        return []
    return [str(x).strip() for x in items if str(x).strip()][:limit]


def terminal_review_message(review: dict, verdict: str, blocker: str) -> str:
    score = review.get("progress_score", "?")
    actions = compact_list(review.get("next_actions", []), 3)
    verified = compact_list(review.get("verified", []), 2)
    unsupported = compact_list(review.get("unsupported_claims", []), 2)
    closure = review.get("closure_audit") or {}
    missed = compact_list(closure.get("release_critical_missed_work", []), 2) if isinstance(closure, dict) else []
    parts = [f"Outcome Fusion {verdict}. Score {score}. Blocker: {blocker or 'none'}"]
    if verified:
        parts.append("Verified: " + "; ".join(verified))
    if unsupported:
        parts.append("Unsupported: " + "; ".join(unsupported))
    if missed:
        parts.append("Closure missed: " + "; ".join(missed))
    if actions:
        parts.append("Next: " + "; ".join(actions))
    return "\n".join(parts)[:1800]


def main() -> int:
    payload = read_stdin_json()
    if not env_bool("OUTCOME_FUSION_ENABLED", True):
        return 0
    if payload.get("stop_hook_active"):
        return 0

    cwd = cwd_from_hook(payload)
    wdir = workspace_dir(cwd, payload)
    mission = safe_read(wdir / "mission.md", limit=50000)
    if not mission.strip():
        return 0

    proof = safe_read(wdir / "proof.md", limit=50000)
    tool_log = safe_read(wdir / "tool_log.md", limit=50000)
    memory = safe_read(wdir / "memory.md", limit=20000)
    transcript = recent_transcript_text(payload.get("transcript_path", ""), limit_chars=50000)
    last_message = payload.get("last_assistant_message", "") or ""
    git_status, git_diff, diff_hash = git_status_and_diff(cwd)
    signals = project_signals(cwd)
    # Scan only Claude's actual final message. Scanning the recent transcript
    # also matched the plugin's own injected rule text ("never say impossible,
    # cannot, ...") and fired a false positive on every turn.
    lazy = contains_lazy_impossible(last_message)

    state_path = make_state_path(payload, cwd)
    state = load_state(state_path)
    if diff_hash == state.get("last_diff_hash"):
        state["same_diff_count"] = int(state.get("same_diff_count", 0)) + 1
    else:
        state["same_diff_count"] = 0
    state["last_diff_hash"] = diff_hash

    max_continues = env_int("OUTCOME_FUSION_MAX_CONTINUES", 5)
    loop_state = {
        "forced_continuations": state.get("continues", 0),
        "same_diff_count": state.get("same_diff_count", 0),
        "last_blocker": state.get("last_blocker", ""),
        "max_continues": max_continues,
    }

    rendered = safe_format(
        PROMPT,
        mission=mission,
        last_message=last_message,
        transcript=transcript,
        signals=signals,
        git_status=git_status,
        diff_hash=diff_hash,
        git_diff=git_diff,
        proof=proof,
        tool_log=tool_log,
        loop_state=json.dumps(loop_state, ensure_ascii=False),
        lazy_impossible=str(lazy),
    )
    # Self-consistency: poll the judge N times and take the majority verdict.
    # Default 3 — the A/B (eval/ab_voting.py) showed 1 sample false-blocks good
    # work (2/5) while 3 perspective-diverse votes did not (0/5). Set to 1 for
    # the cheapest single-call gate. Higher = more reliable, more cost.
    votes = max(1, env_int("OUTCOME_FUSION_GATE_VOTES", 3))
    vote_temp = 0.1 if votes == 1 else 0.4
    lenses = vote_lenses(votes)  # perspective-diverse votes (MoA: diversity drives the gain)
    try:
        reviews: list[dict] = []
        last_raw = ""
        for i in range(votes):
            prompt_i = rendered if not lenses[i] else rendered + "\n\n" + lenses[i]
            one, raw = call_deepseek_json(
                SYSTEM, prompt_i, max_tokens=4200, temperature=vote_temp, timeout=170, require_keys=["verdict"]
            )
            log_metric(wdir, "release_gate", {"verdict": str((one or {}).get("verdict", "")).upper() or None})
            if one:
                reviews.append(one)
            if raw.strip():
                last_raw = raw
        review = aggregate_reviews(reviews) or fallback_review(mission, proof, tool_log, lazy)
        # When voting, persist the aggregated review (incl. the vote breakdown)
        # so the decision is auditable; for a single vote keep the raw reply.
        if votes > 1:
            safe_write(wdir / "review.md", json.dumps(review, ensure_ascii=False, indent=2))
        else:
            safe_write(wdir / "review.md", last_raw if last_raw.strip() else json.dumps(review, indent=2))
        mirror_latest(wdir, "review.md")
    except Exception as e:
        review = fallback_review(mission, proof, tool_log, lazy)
        safe_write(wdir / "last_error.txt", f"release_gate fallback: {e}\n")
        safe_write(wdir / "review.md", json.dumps(review, ensure_ascii=False, indent=2))
        mirror_latest(wdir, "review.md")

    verdict = str(review.get("verdict", "FAIL")).upper()
    blocker = str(review.get("single_blocker") or review.get("biggest_blocker") or "")
    memory_update = str(review.get("memory_update") or "")
    if memory_update.strip():
        append_memory(wdir, memory_update)

    terminal_log = env_bool("OUTCOME_FUSION_TERMINAL_LOG", True)

    if verdict == "PASS":
        state["continues"] = 0
        state["last_blocker"] = ""
        save_state(state_path, state)
        closure = review.get("closure_audit") if isinstance(review.get("closure_audit"), dict) else {}
        closure_text = "# Outcome Fusion Closure\n\n"
        closure_text += f"Verdict: PASS\nScore: {review.get('progress_score', 'unknown')}\nStop reason: {review.get('stop_reason_if_pass', '')}\n\n"
        closure_text += "## If user asks anything else\n" + str(closure.get("if_user_asks_anything_else", "No release critical missed work recorded.")) + "\n\n"
        closure_text += "## Release critical missed work\n" + json.dumps(closure.get("release_critical_missed_work", []), ensure_ascii=False, indent=2) + "\n\n"
        closure_text += "## Non blocking followups\n" + json.dumps(closure.get("non_blocking_followups", []), ensure_ascii=False, indent=2) + "\n\n"
        closure_text += "## Done lock reason\n" + str(closure.get("done_lock_reason", "PASS returned by release gate.")) + "\n"
        safe_write(wdir / "closure.md", closure_text)
        mirror_latest(wdir, "closure.md", closure_text)
        if terminal_log:
            json_stdout({"systemMessage": terminal_review_message(review, verdict, blocker)})
        return 0

    if verdict == "BLOCKED":
        safe_write(wdir / "blocked.md", json.dumps(review, ensure_ascii=False, indent=2))
        state["last_blocker"] = blocker
        save_state(state_path, state)
        if terminal_log:
            json_stdout({"systemMessage": terminal_review_message(review, verdict, blocker)})
        return 0

    if int(state.get("continues", 0)) >= max_continues:
        safe_write(wdir / "blocked.md", "Outcome Fusion reached max continuation rounds. Review manually.\n\n" + json.dumps(review, ensure_ascii=False, indent=2))
        save_state(state_path, state)
        return 0

    if int(state.get("same_diff_count", 0)) >= 3:
        review.setdefault("next_actions", [])
        review["next_actions"] = ["Stop repeating the same path. State why the previous attempts failed, then choose a different strategy."] + list(review.get("next_actions") or [])

    state["continues"] = int(state.get("continues", 0)) + 1
    state["last_blocker"] = blocker
    save_state(state_path, state)

    feedback = f"""
Outcome Fusion Principia review: FAIL

Blocker:
{blocker}

Progress score:
{review.get('progress_score', 'unknown')}

Unsupported claims:
{json.dumps(review.get('unsupported_claims', []), ensure_ascii=False)}

Simplify or remove:
{json.dumps(review.get('simplify_or_remove', []), ensure_ascii=False)}

Non obvious paths:
{json.dumps(review.get('non_obvious_paths', []), ensure_ascii=False)}

Falsification tests:
{json.dumps(review.get('falsification_tests', []), ensure_ascii=False)}

Next actions:
{json.dumps(review.get('next_actions', []), ensure_ascii=False)}

Closure audit:
{json.dumps(review.get('closure_audit', {}), ensure_ascii=False)}

Continue now. Do not ask the user for normal engineering choices. Use first principles, remove unnecessary parts, verify claims, update the session proof ledger below, and do not claim done until this gate returns PASS or a specific evidence based blocker exists.

{session_paths_block(wdir)}
""".strip()

    # "Stop stopping": by default, FAIL forces Claude to continue in the SAME
    # turn (decision: block) instead of just leaving guidance for next time —
    # so the agent keeps working until PASS or the continuation cap. Bounded by
    # OUTCOME_FUSION_MAX_CONTINUES (and the same-diff guard) above. Set
    # OUTCOME_FUSION_AUTOCONTINUE=0 to revert to non-blocking guidance.
    autocontinue = env_bool("OUTCOME_FUSION_AUTOCONTINUE", True)
    reason = feedback + "\n\nContinue now in this same turn without waiting for the user. First print the Outcome Fusion verdict, blocker, and next actions, then keep working."
    out = continue_decision(reason, autocontinue)
    if terminal_log:
        out["systemMessage"] = terminal_review_message(review, verdict, blocker)
    json_stdout(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
