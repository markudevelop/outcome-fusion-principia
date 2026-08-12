"""Behavioural tests for the hooks, driven in-process.

The existing suites mostly assert that doctrine TEXT is present in a prompt.
That catches a deleted rule, but it cannot catch a broken decision: the gate
could block every turn, or allow every turn, and those tests would still pass.

These call each hook's ``main()`` directly with a fake stdin and a stubbed judge,
so the assertions are about what the hook DOES — which file it writes, whether it
blocks, how it counts state. No network, no subprocess, so coverage is real and
the suite stays fast.
"""
from __future__ import annotations

import json
import pathlib
import sys

import batch_feedback
import capture_tool
import common
import compile_prompt
import pytest
import release_gate
import session_context
import stop_failure


# ---- harness ----------------------------------------------------------------

def drive(module, payload: dict, monkeypatch, *, judge=None, compile_text=None, diff=("", "", "h0", [])):
    """Run ``module.main()`` with stdin=payload; return (rc, emitted_json_or_None)."""
    emitted: list[dict] = []
    monkeypatch.setattr(module, "read_stdin_json", lambda: payload, raising=False)
    monkeypatch.setattr(module, "json_stdout", lambda obj: emitted.append(obj), raising=False)
    if judge is not None:
        monkeypatch.setattr(module, "call_deepseek_json", judge, raising=False)
    if compile_text is not None:
        monkeypatch.setattr(module, "call_deepseek", compile_text, raising=False)
    if hasattr(module, "git_status_and_diff"):
        monkeypatch.setattr(module, "git_status_and_diff", lambda *a, **k: diff, raising=False)
    rc = module.main()
    return rc, (emitted[0] if emitted else None)


def verdict_judge(verdict="PASS", **extra):
    """A stubbed judge that always returns the same verdict."""
    def _judge(system, prompt, **kw):
        review = {"verdict": verdict, "progress_score": 90, "single_blocker": "", **extra}
        return review, json.dumps(review)
    return _judge


def build_session(tmp_path, mission="# Mission\nDo it.\n\n# Deliverables checklist\n1. Do it\n",
                  request="do it", intent=common.INTENT_BUILD):
    wdir = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_s1"
    wdir.mkdir(parents=True, exist_ok=True)
    (wdir / "mission.md").write_text(mission, encoding="utf-8")
    (wdir / "request.txt").write_text(request, encoding="utf-8")
    common.write_turn_mode(wdir, intent, request)
    return wdir


def payload_for(tmp_path, **kw):
    return {"cwd": str(tmp_path), "session_id": "s1", "last_assistant_message": "done", **kw}


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    # Vote count is exercised explicitly where it matters; default to 1 so the
    # stub judge is called once per test and call counts stay readable.
    monkeypatch.setenv("OUTCOME_FUSION_GATE_VOTES", "1")
    monkeypatch.setenv("OUTCOME_FUSION_TERMINAL_LOG", "1")
    # Gate state lives OUTSIDE the project (~/.claude/outcome_fusion). Without
    # redirecting it these tests wrote into the user's real state directory and
    # accumulated `continues` across runs until they tripped the continuation
    # cap and started failing for a reason that had nothing to do with the code.
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "plugin_data"))


# ---- release gate: when it must NOT run -------------------------------------

def test_gate_is_off_when_the_plugin_is_disabled(tmp_path, monkeypatch):
    build_session(tmp_path)
    monkeypatch.setenv("OUTCOME_FUSION_ENABLED", "0")
    called = []
    rc, out = drive(release_gate, payload_for(tmp_path), monkeypatch,
                    judge=lambda *a, **k: called.append(1) or ({}, ""))
    assert rc == 0 and out is None
    assert not called, "disabled gate still called the judge"


def test_gate_does_not_recurse_on_its_own_stop(tmp_path, monkeypatch):
    # stop_hook_active means this Stop was triggered by the gate's own block.
    # Without this guard the gate loops on itself forever.
    build_session(tmp_path)
    called = []
    rc, out = drive(release_gate, payload_for(tmp_path, stop_hook_active=True), monkeypatch,
                    judge=lambda *a, **k: called.append(1) or ({}, ""))
    assert rc == 0 and out is None and not called


def test_gate_skips_question_turns(tmp_path, monkeypatch):
    build_session(tmp_path, intent=common.INTENT_QUESTION)
    called = []
    rc, out = drive(release_gate, payload_for(tmp_path), monkeypatch,
                    judge=lambda *a, **k: called.append(1) or ({}, ""))
    assert rc == 0 and out is None
    assert not called, "a question turn was billed for a gate vote"


def test_gate_skips_when_there_is_no_mission(tmp_path, monkeypatch):
    wdir = build_session(tmp_path)
    (wdir / "mission.md").write_text("   \n", encoding="utf-8")
    called = []
    rc, _ = drive(release_gate, payload_for(tmp_path), monkeypatch,
                  judge=lambda *a, **k: called.append(1) or ({}, ""))
    assert rc == 0 and not called


# ---- release gate: verdict handling -----------------------------------------

def test_pass_writes_closure_and_allows_stop(tmp_path, monkeypatch):
    wdir = build_session(tmp_path)
    rc, out = drive(release_gate, payload_for(tmp_path), monkeypatch,
                    judge=verdict_judge("PASS", stop_reason_if_pass="all delivered"))
    assert rc == 0
    assert out is not None and "decision" not in out, "PASS must not block the stop"
    closure = (wdir / "closure.md").read_text(encoding="utf-8")
    assert "Verdict: PASS" in closure and "all delivered" in closure


def test_blocked_writes_blocked_md_and_allows_stop(tmp_path, monkeypatch):
    wdir = build_session(tmp_path)
    rc, out = drive(release_gate, payload_for(tmp_path), monkeypatch,
                    judge=verdict_judge("BLOCKED", single_blocker="needs a paid API key"))
    assert rc == 0
    assert out is not None and "decision" not in out
    assert "needs a paid API key" in (wdir / "blocked.md").read_text(encoding="utf-8")


def test_fail_blocks_the_stop_when_autocontinue_is_on(tmp_path, monkeypatch):
    build_session(tmp_path)
    monkeypatch.setenv("OUTCOME_FUSION_AUTOCONTINUE", "1")
    rc, out = drive(release_gate, payload_for(tmp_path), monkeypatch,
                    judge=verdict_judge("FAIL", single_blocker="docs missing"))
    assert out is not None
    assert out.get("decision") == "block", "FAIL did not force continuation"
    assert "docs missing" in json.dumps(out)


def test_fail_only_advises_when_autocontinue_is_off(tmp_path, monkeypatch):
    build_session(tmp_path)
    monkeypatch.setenv("OUTCOME_FUSION_AUTOCONTINUE", "0")
    rc, out = drive(release_gate, payload_for(tmp_path), monkeypatch,
                    judge=verdict_judge("FAIL", single_blocker="docs missing"))
    assert out is not None
    assert out.get("decision") is None
    assert out["hookSpecificOutput"]["additionalContext"]


def test_gate_stops_forcing_after_max_continues(tmp_path, monkeypatch):
    # Without this bound a FAIL loop never terminates and the user cannot regain
    # control of the turn.
    wdir = build_session(tmp_path)
    monkeypatch.setenv("OUTCOME_FUSION_AUTOCONTINUE", "1")
    monkeypatch.setenv("OUTCOME_FUSION_MAX_CONTINUES", "2")
    payload = payload_for(tmp_path)
    state_path = common.make_state_path(payload, tmp_path)
    common.save_state(state_path, {"continues": 2})

    rc, out = drive(release_gate, payload, monkeypatch, judge=verdict_judge("FAIL"))
    assert rc == 0
    assert out is None or out.get("decision") != "block", "gate kept blocking past the cap"
    assert "max continuation rounds" in (wdir / "blocked.md").read_text(encoding="utf-8")


def test_pass_resets_the_continuation_counter(tmp_path, monkeypatch):
    build_session(tmp_path)
    payload = payload_for(tmp_path)
    state_path = common.make_state_path(payload, tmp_path)
    common.save_state(state_path, {"continues": 3, "last_blocker": "old"})
    drive(release_gate, payload, monkeypatch, judge=verdict_judge("PASS"))
    state = common.load_state(state_path)
    assert state["continues"] == 0 and state["last_blocker"] == ""


def test_repeated_identical_diff_is_counted(tmp_path, monkeypatch):
    # same_diff_count is what tells the judge "you changed nothing since last
    # time", which is how the loop escapes repeating a failed strategy.
    build_session(tmp_path)
    payload = payload_for(tmp_path)
    state_path = common.make_state_path(payload, tmp_path)
    monkeypatch.setenv("OUTCOME_FUSION_AUTOCONTINUE", "0")
    for _ in range(3):
        drive(release_gate, payload, monkeypatch, judge=verdict_judge("FAIL"),
              diff=("M f.py", "@@ same", "SAME_HASH", []))
    assert common.load_state(state_path)["same_diff_count"] >= 2


def test_changed_diff_resets_the_same_diff_counter(tmp_path, monkeypatch):
    build_session(tmp_path)
    payload = payload_for(tmp_path)
    state_path = common.make_state_path(payload, tmp_path)
    monkeypatch.setenv("OUTCOME_FUSION_AUTOCONTINUE", "0")
    drive(release_gate, payload, monkeypatch, judge=verdict_judge("FAIL"), diff=("", "", "H1", []))
    drive(release_gate, payload, monkeypatch, judge=verdict_judge("FAIL"), diff=("", "", "H1", []))
    drive(release_gate, payload, monkeypatch, judge=verdict_judge("FAIL"), diff=("", "", "H2", []))
    assert common.load_state(state_path)["same_diff_count"] == 0


def test_judge_failure_falls_back_instead_of_crashing(tmp_path, monkeypatch):
    # A hook that raises kills the turn. It must degrade to the heuristic.
    wdir = build_session(tmp_path)
    monkeypatch.setenv("OUTCOME_FUSION_AUTOCONTINUE", "0")

    def boom(*a, **k):
        raise RuntimeError("HTTP 401 invalid x-api-key")

    rc, out = drive(release_gate, payload_for(tmp_path), monkeypatch, judge=boom)
    assert rc == 0
    assert "401" in (wdir / "last_error.txt").read_text(encoding="utf-8")
    assert (wdir / "review.md").read_text(encoding="utf-8").strip()


def test_secret_in_the_diff_fails_closed_even_when_the_judge_dies(tmp_path, monkeypatch):
    # The combination that used to ship a credential: no working judge AND a
    # credential in the diff. The heuristic must FAIL, not allow the stop.
    build_session(tmp_path)
    monkeypatch.setenv("OUTCOME_FUSION_AUTOCONTINUE", "1")

    def boom(*a, **k):
        raise RuntimeError("no key")

    rc, out = drive(release_gate, payload_for(tmp_path), monkeypatch, judge=boom,
                    diff=("M cfg.py", "+API_KEY = 'x'", "h9", ["app/cfg.py:1: hardcoded key/token/password literal"]))
    assert out is not None and out.get("decision") == "block"
    assert "rotate" in json.dumps(out).lower()


def test_memory_update_is_appended(tmp_path, monkeypatch):
    wdir = build_session(tmp_path)
    drive(release_gate, payload_for(tmp_path), monkeypatch,
          judge=verdict_judge("PASS", memory_update="Never trust a green suite with skips."))
    assert "Never trust a green suite" in (wdir / "memory.md").read_text(encoding="utf-8")


def test_votes_greater_than_one_persist_the_aggregate(tmp_path, monkeypatch):
    wdir = build_session(tmp_path)
    monkeypatch.setenv("OUTCOME_FUSION_GATE_VOTES", "3")
    calls = []

    def judge(system, prompt, **kw):
        calls.append(prompt)
        return {"verdict": "PASS", "progress_score": 90}, '{"verdict": "PASS"}'

    drive(release_gate, payload_for(tmp_path), monkeypatch, judge=judge)
    assert len(calls) == 3, "vote count not honoured"
    assert len(set(calls)) == 3, "votes were identical; the lenses add no diversity"
    assert json.loads((wdir / "review.md").read_text(encoding="utf-8"))["verdict"] == "PASS"


# ---- compile_prompt ---------------------------------------------------------

def test_question_turn_writes_no_mission(tmp_path, monkeypatch):
    rc, out = drive(compile_prompt, {"cwd": str(tmp_path), "session_id": "q1",
                                     "prompt": "what does the gate do?"}, monkeypatch)
    assert rc == 0
    wdir = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_q1"
    assert not (wdir / "mission.md").exists()
    assert "QUESTION" in json.dumps(out).upper()


def test_build_turn_writes_mission_and_verbatim_request(tmp_path, monkeypatch):
    doc = "# Mission\nShip it.\n\n# Deliverables checklist\n1. Ship it\n"
    rc, out = drive(compile_prompt, {"cwd": str(tmp_path), "session_id": "b1",
                                     "prompt": "ship the thing"}, monkeypatch,
                    compile_text=lambda *a, **k: doc)
    wdir = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_b1"
    assert (wdir / "mission.md").read_text(encoding="utf-8").startswith("# Mission")
    assert (wdir / "request.txt").read_text(encoding="utf-8").strip() == "ship the thing"


def test_compiler_strips_reasoning_before_writing(tmp_path, monkeypatch):
    leaked = ("We need to parse the user prompt and think about the structure.\n\n"
              "# Mission\nShip it.\n\n# Deliverables checklist\n1. Ship it\n")
    drive(compile_prompt, {"cwd": str(tmp_path), "session_id": "b2", "prompt": "ship it"},
          monkeypatch, compile_text=lambda *a, **k: leaked)
    mission = (tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_b2" / "mission.md").read_text(encoding="utf-8")
    assert mission.startswith("# Mission")
    assert "We need to parse" not in mission


def test_compiler_retries_then_falls_back_on_unusable_output(tmp_path, monkeypatch):
    attempts = []

    def always_garbage(system, body, **kw):
        attempts.append(system)
        return "We need to think about this and then we will decide what to do."

    drive(compile_prompt, {"cwd": str(tmp_path), "session_id": "b3", "prompt": "ship it"},
          monkeypatch, compile_text=always_garbage)
    wdir = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_b3"
    mission = (wdir / "mission.md").read_text(encoding="utf-8")

    assert len(attempts) == 2, "compiler did not retry once before falling back"
    assert "emitted reasoning instead of the document" in attempts[1], "retry did not name the failure mode"
    assert common.mission_is_usable(mission), "wrote an unusable mission"
    assert "no usable mission twice" in (wdir / "last_error.txt").read_text(encoding="utf-8")


def test_compiler_second_attempt_can_succeed(tmp_path, monkeypatch):
    good = "# Mission\nShip.\n\n# Deliverables checklist\n1. Ship\n"
    seq = ["We need to think about it...", good]
    drive(compile_prompt, {"cwd": str(tmp_path), "session_id": "b4", "prompt": "ship it"},
          monkeypatch, compile_text=lambda *a, **k: seq.pop(0))
    mission = (tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_b4" / "mission.md").read_text(encoding="utf-8")
    assert mission.startswith("# Mission") and common.mission_is_usable(mission)


def test_compile_falls_back_when_the_api_raises(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("connection refused")

    drive(compile_prompt, {"cwd": str(tmp_path), "session_id": "b5", "prompt": "ship it"},
          monkeypatch, compile_text=boom)
    wdir = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_b5"
    assert common.mission_is_usable((wdir / "mission.md").read_text(encoding="utf-8"))
    assert "connection refused" in (wdir / "last_error.txt").read_text(encoding="utf-8")


# ---- the other three hooks --------------------------------------------------

def test_session_context_emits_the_workspace_paths_when_there_is_a_mission(tmp_path, monkeypatch):
    wdir = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_sc1"
    wdir.mkdir(parents=True)
    (wdir / "mission.md").write_text("# Mission\nCarry on.\n\n# Deliverables checklist\n1. Carry on\n", encoding="utf-8")
    rc, out = drive(session_context, {"cwd": str(tmp_path), "session_id": "sc1",
                                      "hook_event_name": "SessionStart"}, monkeypatch)
    assert rc == 0
    blob = json.dumps(out)
    assert "sid_sc1" in blob, "session paths not injected at SessionStart"
    assert "Carry on" in blob, "mission preview not injected"


def test_session_context_stays_silent_on_a_fresh_session(tmp_path, monkeypatch):
    # No mission and no memory yet: injecting an empty scaffold would spend
    # context on nothing. Silence is the correct behaviour here.
    rc, out = drive(session_context, {"cwd": str(tmp_path), "session_id": "sc2",
                                      "hook_event_name": "SessionStart"}, monkeypatch)
    assert rc == 0 and out is None


def test_session_context_seeds_the_proof_ledger(tmp_path, monkeypatch):
    wdir = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_sc3"
    wdir.mkdir(parents=True)
    (wdir / "mission.md").write_text("# Mission\nx\n\n# Deliverables checklist\n1. x\n", encoding="utf-8")
    drive(session_context, {"cwd": str(tmp_path), "session_id": "sc3"}, monkeypatch)
    assert "Proof ledger" in (wdir / "proof.md").read_text(encoding="utf-8")


def test_resume_reconnects_to_the_existing_workspace(tmp_path, monkeypatch):
    # On /resume Claude Code may hand over a NEW session_id while keeping the
    # transcript path. Without reconnection the session silently starts a fresh
    # workspace and loses its mission, proof ledger, and closure.
    old = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_original"
    old.mkdir(parents=True)
    (old / "mission.md").write_text("# Mission\nOriginal work.\n\n# Deliverables checklist\n1. Original\n", encoding="utf-8")
    (old / "_session_meta.json").write_text(json.dumps({"transcript_path": "/tmp/t.jsonl"}), encoding="utf-8")

    rc, out = drive(session_context, {"cwd": str(tmp_path), "session_id": "brand-new-id",
                                      "transcript_path": "/tmp/t.jsonl", "source": "resume"}, monkeypatch)
    assert rc == 0
    assert "Original work" in json.dumps(out), "resume did not reconnect to the prior workspace"


def test_stop_failure_hook_records_and_exits_clean(tmp_path, monkeypatch):
    rc, _ = drive(stop_failure, {"cwd": str(tmp_path), "session_id": "sf1",
                                 "hook_event_name": "StopFailure", "error": "boom"}, monkeypatch)
    assert rc == 0


def test_batch_feedback_hook_exits_clean(tmp_path, monkeypatch):
    rc, _ = drive(batch_feedback, {"cwd": str(tmp_path), "session_id": "bf1",
                                   "hook_event_name": "PostToolBatch"}, monkeypatch)
    assert rc == 0


@pytest.mark.parametrize("module", [release_gate, compile_prompt, session_context,
                                    stop_failure, batch_feedback, capture_tool])
def test_no_hook_crashes_on_an_empty_payload(module, monkeypatch, tmp_path):
    # Claude Code can invoke a hook with fields missing. A traceback here kills
    # the user's turn, so every hook must survive an empty payload.
    monkeypatch.chdir(tmp_path)
    rc, _ = drive(module, {}, monkeypatch,
                  judge=verdict_judge("PASS"), compile_text=lambda *a, **k: "# Mission\nx\n\n# Deliverables checklist\n1. x\n")
    assert rc == 0


# ---- aggregation and formatting primitives ----------------------------------

def test_majority_fail_wins_the_vote():
    assert common.aggregate_reviews([{"verdict": "FAIL"}, {"verdict": "PASS"}, {"verdict": "FAIL"}])["verdict"] == "FAIL"


def test_majority_pass_wins_the_vote():
    assert common.aggregate_reviews([{"verdict": "PASS"}, {"verdict": "PASS"}, {"verdict": "FAIL"}])["verdict"] == "PASS"


def test_a_split_vote_does_not_silently_pass():
    # With no majority the safe direction is to keep working, not to ship.
    out = common.aggregate_reviews([{"verdict": "PASS"}, {"verdict": "FAIL"}])
    assert out["verdict"] in ("FAIL", "BLOCKED")


def test_aggregate_of_nothing_is_falsy():
    assert not common.aggregate_reviews([])


def test_safe_format_survives_braces_in_the_payload():
    # A diff containing JSON used to raise KeyError and take the gate down.
    out = common.safe_format("A {x} B", x='{"nested": {"json": 1}}')
    assert '"nested"' in out


def test_safe_format_tolerates_a_missing_placeholder():
    assert "{unknown}" in common.safe_format("keep {unknown} here", x="1")


@pytest.mark.parametrize("raw,secret", [
    ('API_KEY = "sk-abcdefghijklmnop"', "sk-abcdefghijklmnop"),
    ("Authorization: Bearer abc123def456", "abc123def456"),
    ('password: "hunter2hunter2"', "hunter2hunter2"),
])
def test_redact_removes_credentials_before_they_leave(raw, secret):
    assert secret not in common.redact(raw)


def test_mission_deliverables_parses_the_checklist():
    mission = ("# Mission\nx\n\n# Deliverables checklist\n"
               "1. First thing\n2. Second thing\n3. Third thing\n\n# Simplification mandate\n- none\n")
    items = common.mission_deliverables(mission)
    assert items == ["First thing", "Second thing", "Third thing"]


def test_mission_deliverables_is_empty_when_there_is_no_checklist():
    assert common.mission_deliverables("# Mission\njust do it\n") == []


# ---- gate state isolation ---------------------------------------------------

def test_state_does_not_collide_between_repos_with_the_same_folder_name(tmp_path):
    # /work/clientA/app and /work/clientB/app used to share one state file, so
    # working in one moved the other's continuation counter and diff hash.
    a = tmp_path / "clientA" / "app"
    b = tmp_path / "clientB" / "app"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    pa = common.make_state_path({"session_id": "s1"}, a)
    pb = common.make_state_path({"session_id": "s1"}, b)
    assert pa != pb, "two different repos still share one gate state file"
    assert "app" in pa.name, "readable prefix lost"


def test_state_is_stable_for_the_same_project_and_session(tmp_path):
    # The disambiguator must be deterministic, or every turn starts from zero
    # and the continuation cap never engages.
    p = tmp_path / "repo"
    p.mkdir()
    first = common.make_state_path({"session_id": "s1"}, p)
    second = common.make_state_path({"session_id": "s1"}, p)
    assert first == second


def test_state_separates_sessions_within_one_project(tmp_path):
    p = tmp_path / "repo"
    p.mkdir()
    assert common.make_state_path({"session_id": "s1"}, p) != common.make_state_path({"session_id": "s2"}, p)


def test_tests_never_touch_the_real_plugin_data_dir(tmp_path, monkeypatch):
    # Regression guard for the pollution this suite caused: 16 state files
    # written into the user's ~/.claude/outcome_fusion during development.
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "pd"))
    d = common.plugin_data_dir({})
    assert str(tmp_path) in str(d)
    assert ".claude" not in str(d) or str(tmp_path) in str(d)


# ---- capture_tool -----------------------------------------------------------

def _capture(tmp_path, monkeypatch, cmd="pytest -q", event="PostToolUse", tool="Bash", response="2 passed"):
    payload = {"cwd": str(tmp_path), "session_id": "c1", "hook_event_name": event,
               "tool_name": tool, "tool_input": {"command": cmd}, "tool_response": response}
    rc, out = drive(capture_tool, payload, monkeypatch)
    wdir = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_c1"
    return rc, out, wdir


def test_capture_logs_every_tool_call(tmp_path, monkeypatch):
    rc, _, wdir = _capture(tmp_path, monkeypatch, cmd="ls -la")
    assert rc == 0
    assert "ls -la" in (wdir / "tool_log.md").read_text(encoding="utf-8")


def test_capture_records_a_verification_command_in_the_proof_ledger(tmp_path, monkeypatch):
    rc, out, wdir = _capture(tmp_path, monkeypatch, cmd='cd "C:/repo" && pytest -q')
    proof = (wdir / "proof.md").read_text(encoding="utf-8")
    assert "check ran: `pytest -q`" in proof, proof
    assert "Interpret the result" in json.dumps(out), "the interpret nudge is the useful half"


def test_capture_ignores_commands_that_verify_nothing(tmp_path, monkeypatch):
    # `ls` is not evidence; recording it would dilute the ledger the judge reads.
    rc, _, wdir = _capture(tmp_path, monkeypatch, cmd="ls -la")
    assert not (wdir / "proof.md").exists() or "check ran" not in (wdir / "proof.md").read_text(encoding="utf-8")


def test_capture_dedups_the_same_check_across_directories(tmp_path, monkeypatch):
    _capture(tmp_path, monkeypatch, cmd="pytest -q")
    _capture(tmp_path, monkeypatch, cmd='cd "C:/elsewhere" && pytest -q')
    _capture(tmp_path, monkeypatch, cmd="pytest -q")
    wdir = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_c1"
    assert (wdir / "proof.md").read_text(encoding="utf-8").count("check ran: `pytest -q`") == 1


def test_capture_entry_stays_compact(tmp_path, monkeypatch):
    # The old four-line stub was ~900 chars and crowded real claims out of the
    # judge's 30k window.
    _, _, wdir = _capture(tmp_path, monkeypatch, cmd="pytest -q")
    line = [l for l in (wdir / "proof.md").read_text(encoding="utf-8").splitlines() if "check ran" in l][0]
    assert len(line) < 120, f"{len(line)} chars"


def test_tool_failure_tells_claude_to_change_hypothesis(tmp_path, monkeypatch):
    rc, out, _ = _capture(tmp_path, monkeypatch, event="PostToolUseFailure", response="boom")
    assert "change the hypothesis" in json.dumps(out).lower()


def test_capture_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTCOME_FUSION_CAPTURE_ENABLED", "0")
    rc, _, wdir = _capture(tmp_path, monkeypatch)
    assert rc == 0
    assert not (wdir / "tool_log.md").exists()
