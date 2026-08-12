"""Tests for the v0.7.0 operating doctrine.

These defaults are model agnostic: they are injected on every turn regardless of
which model drives the session, and nothing in them keys off a model name.

Provenance — two sources drove them, and they disagree in one place:

* Anthropic, "Prompting Claude Opus 5" — Opus 5 self-verifies, expands scope,
  narrates more, and delegates more readily. It says to REMOVE explicit
  verification / re-check instructions and legacy harness scaffolding that adds
  separate verification steps, and to cap subagent spawning.
* productcompass.pm, "How to Heal Claude Opus 5" — add "act don't ask",
  "a question is a question", and "done means done" blocks.

Resolution locked by these tests: the plugin keeps verification only where it is
OUT OF BAND (the release gate: a different model judging finished work) and never
as a "check yourself again" instruction aimed at the agent.
"""
from __future__ import annotations

import importlib
import json
import os
import pathlib
import re
import subprocess
import sys

import common
import compile_prompt
import pytest
import release_gate

PLUGIN = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = PLUGIN / "scripts"


# ---- intent router ----------------------------------------------------------

QUESTIONS = [
    "what does the release gate actually do?",
    "why is the same-diff guard needed?",
    "how does the voting aggregation resolve a tie?",
    "is GATE_VOTES=3 worth the cost?",
    "explain the session workspace layout",
    "should we keep the autocontinue loop",
    "which lens catches the most false passes?",
    "does the gate see memory.md?",
    "compare votes=1 and votes=3",
    "tell me about the proof ledger",
]

BUILDS = [
    "add an intent router to the plugin",
    "fix the release gate false positives",
    "implement question mode and ship it",
    "can you add a cost command?",            # question-shaped, but a build verb
    "how do I add caching here?",             # ditto: bias to build is deliberate
    "refactor common.py",
    "run the tests",
    "please update the README and push",
    "the gate is too expensive, optimize it",
    "backtest the new thresholds",
]

# Real prompts from this project's transcripts that the first version of the
# classifier put in question mode by mistake. Each one is a work order.
REAL_PROMPTS_THAT_MUST_BE_BUILDS = [
    "do it all",                                                   # bare imperative "do"
    "do 2% for her",
    "do it + why dry lets do 1 contract?",
    "set http.version globally and move artifacts out of git + why we move out of git?",
    "ok lets use the new one + confirm if we increased % risk for it as well?",
    "i want bigger universe test and all this rules ideally we have rolling best rule?",
    "i need this on the website we already have something no?",
    "all of this should be commited so i dont lose it",             # "should be"
    "can you brute force more rules",
    "again it seems we had an issue with github actions publisihng weights?",   # defect report
    "the live published weights on the website show trade history wrong?",
    "why i have no signal for today? market is open",
]


@pytest.mark.parametrize("prompt", REAL_PROMPTS_THAT_MUST_BE_BUILDS)
def test_real_world_work_orders_are_not_question_mode(prompt):
    assert common.classify_intent(prompt) == common.INTENT_BUILD, prompt


@pytest.mark.parametrize("prompt", [
    "do you have a quant skill for this?",
    "do we have an iron fly backtester?",
    "do they charge for the settlement feed?",
])
def test_do_you_and_do_we_stay_questions(prompt):
    assert common.classify_intent(prompt) == common.INTENT_QUESTION, prompt


def test_closure_queries_stay_in_build_mode(tmp_path):
    # "anything else?" reads as a question, but its answer can resume work, so
    # the closure path must keep the gate armed.
    assert compile_prompt.is_anything_else_query("anything else?")
    assert common.classify_intent("anything else?") == common.INTENT_QUESTION

    payload = {"cwd": str(tmp_path), "session_id": "s-closure", "prompt": "anything else?"}
    rc, out = _run_hook("compile_prompt.py", payload, tmp_path)
    assert rc == 0
    assert "Closure mode is active" in out
    wdir = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_s-closure"
    assert json.loads((wdir / "turn_mode.json").read_text())["intent"] == "build"


def test_defect_vocabulary_wins_over_question_shape():
    # "issue"/"wrong"/"failing" flip a question-shaped prompt to build. This
    # over-triggers on innocent uses ("does my chip have warranty for this
    # issue?") and that is the intended trade: a false build costs a mission,
    # a false question risks a bug going unfixed.
    assert common.classify_intent("does my chip have warranty for this issue?") == common.INTENT_BUILD


@pytest.mark.parametrize("prompt", QUESTIONS)
def test_questions_classified_as_questions(prompt):
    assert common.classify_intent(prompt) == common.INTENT_QUESTION, prompt


@pytest.mark.parametrize("prompt", BUILDS)
def test_builds_classified_as_builds(prompt):
    assert common.classify_intent(prompt) == common.INTENT_BUILD, prompt


def test_ambiguous_prompt_defaults_to_build():
    # Unknown shape must keep the full apparatus: losing the mission is the
    # safer failure than implementing something nobody asked for.
    assert common.classify_intent("the parquet loader, thoughts on the naming") == common.INTENT_BUILD


def test_explicit_prefixes_override_classification():
    assert common.classify_intent("build: what does this do?") == common.INTENT_BUILD
    assert common.classify_intent("q: fix the failing test") == common.INTENT_QUESTION


def test_router_can_be_disabled(monkeypatch):
    monkeypatch.setenv("OUTCOME_FUSION_INTENT_ROUTER", "0")
    assert common.classify_intent("what does this do?") == common.INTENT_BUILD


def test_empty_prompt_is_build():
    assert common.classify_intent("") == common.INTENT_BUILD


# ---- turn mode round trip ---------------------------------------------------

def test_turn_mode_round_trip(tmp_path):
    common.write_turn_mode(tmp_path, common.INTENT_QUESTION, "what is this?")
    assert common.read_turn_mode(tmp_path) == common.INTENT_QUESTION
    common.write_turn_mode(tmp_path, common.INTENT_BUILD, "fix it")
    assert common.read_turn_mode(tmp_path) == common.INTENT_BUILD


def test_turn_mode_defaults_to_build_when_missing_or_corrupt(tmp_path):
    assert common.read_turn_mode(tmp_path) == common.INTENT_BUILD
    (tmp_path / "turn_mode.json").write_text("not json", encoding="utf-8")
    assert common.read_turn_mode(tmp_path) == common.INTENT_BUILD
    (tmp_path / "turn_mode.json").write_text('{"intent": "nonsense"}', encoding="utf-8")
    assert common.read_turn_mode(tmp_path) == common.INTENT_BUILD


# ---- over-verification instructions are gone --------------------------------

BANNED_SELF_VERIFY = [
    "double-check",
    "double check",
    "re-verify",
    "reverify",
    "verify again",
    "use a subagent to verify",
    "final verification step",
]


def _claude_facing_text() -> str:
    """Everything this plugin injects into Claude's context."""
    return "\n".join([
        compile_prompt.TEMPLATE,
        common.AGENT_OPERATING_BLOCK,
        common.QUESTION_MODE_CONTEXT,
        common.default_mission("p", pathlib.Path(".")),
        (PLUGIN / "skills" / "principia" / "SKILL.md").read_text(encoding="utf-8"),
    ]).lower()


@pytest.mark.parametrize("phrase", BANNED_SELF_VERIFY)
def test_no_self_recheck_instructions_are_injected(phrase):
    text = _claude_facing_text()
    # The only allowed occurrences are inside an explicit "do not" clause.
    for line in text.splitlines():
        if phrase in line:
            assert ("do not" in line or "don't" in line or "never" in line), (
                f"self-recheck instruction still injected: {line.strip()}"
            )


def test_injected_context_no_longer_carries_the_closure_rule():
    # Rule 8 of v0.6.0 told Claude to run an internal "anything else?" audit
    # before every final answer. Anthropic's guide says to remove exactly this.
    src = (SCRIPTS / "compile_prompt.py").read_text(encoding="utf-8")
    build_context = src.split("Core operating rules:")[1].split('""".strip()')[0]
    assert "internal closure question" not in build_context


def test_gate_still_runs_the_closure_audit():
    # Out-of-band verification is kept: the judge, not Claude, owns closure.
    assert "closure_audit" in release_gate.PROMPT
    assert "anything else" in release_gate.PROMPT.lower()


# ---- Opus 5 operating block content ----------------------------------------

@pytest.mark.parametrize("needle", [
    "scope",           # scope control
    "done means done", # complete every requested item
    "act, don't ask",  # reversible work without permission
    "narration",       # progress-update cadence
    "corrections",     # correction narration
    "delegation",      # subagent cap
])
def test_operating_block_covers_each_behaviour_lever(needle):
    assert needle in common.AGENT_OPERATING_BLOCK.lower()


def test_question_mode_context_forbids_unrequested_implementation():
    low = common.QUESTION_MODE_CONTEXT.lower()
    assert "not a mandate to implement" in low
    assert "do not change the project" in low
    assert "answer it" in low


def test_gate_doctrine_refuses_to_fail_for_out_of_scope_work():
    low = release_gate.SYSTEM.lower()
    assert "non_blocking_followups" in low
    assert "never to expand it" in low
    assert "do not fail for the absence of a separate verification pass" in low


# ---- payload budget + effort ------------------------------------------------

def test_gate_payload_limits_are_env_tunable():
    src = (SCRIPTS / "release_gate.py").read_text(encoding="utf-8")
    for var in (
        "OUTCOME_FUSION_MAX_PROOF_CHARS",
        "OUTCOME_FUSION_MAX_TOOLLOG_CHARS",
        "OUTCOME_FUSION_MAX_TRANSCRIPT_CHARS",
    ):
        assert var in src, var
    assert "OUTCOME_FUSION_MAX_DIFF_CHARS" in (SCRIPTS / "common.py").read_text(encoding="utf-8")


def test_gate_no_longer_reads_memory_it_never_sends():
    src = (SCRIPTS / "release_gate.py").read_text(encoding="utf-8")
    assert 'safe_read(wdir / "memory.md"' not in src


def test_call_deepseek_accepts_per_call_effort(monkeypatch):
    seen = {}

    class FakeResp:
        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, *a):
            return False

        def read(self_inner):
            return json.dumps({"content": [{"type": "text", "text": "ok"}], "usage": {}}).encode()

    def fake_urlopen(req, timeout=0):
        seen.update(json.loads(req.data.decode()))
        return FakeResp()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(common, "urlopen", fake_urlopen)
    common.call_deepseek("sys", "user", effort="medium")
    assert seen["output_config"]["effort"] == "medium"


def test_compile_uses_lower_effort_than_the_gate():
    src = (SCRIPTS / "compile_prompt.py").read_text(encoding="utf-8")
    assert 'OUTCOME_FUSION_COMPILE_EFFORT", "medium"' in src


# ---- end to end: a question costs nothing and gates nothing -----------------

def _run_hook(script: str, payload: dict, cwd: pathlib.Path) -> tuple[int, str]:
    env = dict(os.environ)
    env.pop("DEEPSEEK_API_KEY", None)          # force the no-key path
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    env["OUTCOME_FUSION_TERMINAL_LOG"] = "0"
    p = subprocess.run(
        [sys.executable, str(SCRIPTS / script)],
        input=json.dumps(payload),
        capture_output=True, text=True, cwd=str(cwd), env=env, timeout=120,
    )
    return p.returncode, p.stdout


def test_question_turn_compiles_no_mission_and_skips_the_gate(tmp_path):
    payload = {"cwd": str(tmp_path), "session_id": "s-question", "prompt": "what does the gate do?"}
    rc, out = _run_hook("compile_prompt.py", payload, tmp_path)
    assert rc == 0
    assert "not a mandate to implement" in out

    wdir = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_s-question"
    assert not (wdir / "mission.md").exists(), "question mode must not compile a mission"
    assert json.loads((wdir / "turn_mode.json").read_text())["intent"] == "question"

    # A stale mission from an earlier build turn must not re-arm the gate.
    (wdir / "mission.md").write_text("# Mission\nold build work\n", encoding="utf-8")
    rc, out = _run_hook("release_gate.py", {**payload, "last_assistant_message": "Here is the answer."}, tmp_path)
    assert rc == 0
    assert out.strip() == "", "gate must stay silent on a question turn"
    assert not (wdir / "review.md").exists(), "gate must not judge a question turn at all"


def test_build_turn_still_compiles_a_mission_and_arms_the_gate(tmp_path):
    payload = {"cwd": str(tmp_path), "session_id": "s-build", "prompt": "add an intent router"}
    rc, out = _run_hook("compile_prompt.py", payload, tmp_path)
    assert rc == 0

    wdir = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_s-build"
    assert (wdir / "mission.md").exists()
    assert json.loads((wdir / "turn_mode.json").read_text())["intent"] == "build"
    assert "Operating mode:" in out

    # With no API key the gate falls back to the heuristic, which PASSes quietly.
    # Proof that it ran at all is the review it writes.
    rc, _ = _run_hook("release_gate.py", {**payload, "last_assistant_message": "Done."}, tmp_path)
    assert rc == 0
    assert (wdir / "review.md").exists(), "gate must still judge a build turn"


# ---- done means done: mechanical deliverable tracking -----------------------

MISSION_WITH_CHECKLIST = """# Mission
Do three things.

# Deliverables checklist
1. Add the intent router
2. Write the docs
3. Bump the version

# Simplification mandate
Remove the dead memory read.
"""


def test_deliverables_are_extracted_from_the_mission():
    assert common.mission_deliverables(MISSION_WITH_CHECKLIST) == [
        "Add the intent router", "Write the docs", "Bump the version",
    ]


def test_extract_section_stops_at_the_next_heading():
    body = common.extract_section(MISSION_WITH_CHECKLIST, "Deliverables checklist")
    assert "Bump the version" in body
    assert "Remove the dead memory read" not in body


def test_extract_section_missing_heading_is_empty():
    assert common.extract_section(MISSION_WITH_CHECKLIST, "Nonexistent") == ""
    assert common.mission_deliverables("# Mission\nno checklist here\n") == []


def test_parse_checklist_handles_bullets_and_numbers():
    assert common.parse_checklist("- one\n2) two\n* three\nnot an item") == ["one", "two", "three"]


def test_compile_template_demands_one_line_per_request():
    low = compile_prompt.TEMPLATE.lower()
    assert "deliverables checklist" in low
    assert "five things" in low          # the explicit five-means-five instruction


def test_gate_schema_and_rules_track_each_deliverable():
    assert "deliverables_status" in release_gate.PROMPT
    low = release_gate.PROMPT.lower()
    assert "done means done" in low
    assert "four of five" in low         # partial delivery is a FAIL, not a PASS


def test_gate_sees_the_verbatim_request_not_only_the_rewrite():
    assert "{user_request}" in release_gate.PROMPT
    assert "the request wins" in release_gate.PROMPT


def test_terminal_message_reports_delivered_count():
    msg = release_gate.terminal_review_message(
        {
            "progress_score": 80,
            "deliverables_status": [
                {"item": "Add the intent router", "status": "done"},
                {"item": "Write the docs", "status": "missing"},
            ],
        },
        "FAIL", "docs not written",
    )
    assert "Delivered: 1/2 requested items" in msg
    assert "Write the docs" in msg


def test_compile_persists_the_verbatim_request(tmp_path):
    prompt = "add an intent router and write the docs"
    rc, _ = _run_hook("compile_prompt.py",
                      {"cwd": str(tmp_path), "session_id": "s-req", "prompt": prompt}, tmp_path)
    assert rc == 0
    wdir = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_s-req"
    assert (wdir / "request.txt").read_text(encoding="utf-8").strip() == prompt


# ---- credential routing -----------------------------------------------------

def test_deepseek_key_never_routes_to_anthropic_host(monkeypatch):
    # ANTHROPIC_BASE_URL is set in ordinary environments (Claude Code, gateways).
    # Falling back to it posted the DeepSeek key to Anthropic: a permanent 401
    # that silently degraded the gate, and a credential sent to the wrong host.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    monkeypatch.delenv("DEEPSEEK_ANTHROPIC_BASE_URL", raising=False)
    assert common.get_base_url() == common.DEFAULT_BASE_URL
    assert "anthropic.com" not in common.get_base_url()


def test_anthropic_base_url_still_honoured_for_an_anthropic_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://gateway.internal/v1")
    assert common.get_base_url() == "https://gateway.internal/v1"


def test_explicit_override_always_wins(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test")
    monkeypatch.setenv("DEEPSEEK_ANTHROPIC_BASE_URL", "https://proxy.local/anthropic/")
    assert common.get_base_url() == "https://proxy.local/anthropic"


# ---- the doctrine is model agnostic ----------------------------------------

@pytest.mark.parametrize("path", [
    "scripts/common.py", "scripts/compile_prompt.py", "scripts/release_gate.py",
    "skills/principia/SKILL.md",
])
def test_no_model_name_leaks_into_injected_text(path):
    # Provenance may be cited in comments, but nothing the agent or the judge
    # reads may key off a specific model name or version.
    text = (PLUGIN / path).read_text(encoding="utf-8")
    injected = "\n".join(
        ln for ln in text.splitlines()
        if not ln.lstrip().startswith("#")
    ).lower()
    for name in ("opus 5", "opus5", "fable", "sonnet", "gpt-"):
        assert name not in injected, f"{path} injects a model-specific string: {name}"


# ---- the eval suite itself stays valid --------------------------------------

def _load_scenarios():
    sys.path.insert(0, str(PLUGIN / "eval"))
    import run_eval
    return run_eval


def test_eval_scenarios_are_well_formed():
    run_eval = _load_scenarios()
    ids = [s["id"] for s in run_eval.SCENARIOS]
    assert len(ids) == len(set(ids)), "duplicate scenario ids"
    assert len(ids) >= 38, "scenario set shrank"
    for s in run_eval.SCENARIOS:
        for key in ("id", "label", "mission", "diff", "proof", "tool_log", "final"):
            assert key in s, f"{s['id']} missing {key}"
        assert s["label"] in ("good", "bad"), s["id"]


def test_eval_covers_every_domain_with_both_labels():
    run_eval = _load_scenarios()
    seen = {}
    for s in run_eval.SCENARIOS:
        seen.setdefault(s.get("domain", "eng"), set()).add(s["label"])
    for domain in ("eng", "advanced", "quant", "generic"):
        assert seen.get(domain) == {"good", "bad"}, f"{domain} needs both good and bad cases"


def test_eval_harness_supplies_every_gate_placeholder():
    # A missing field would leave a literal "{user_request}" in the judge prompt
    # and quietly invalidate the whole measurement.
    run_eval = _load_scenarios()
    s = next(x for x in run_eval.SCENARIOS if x["id"] == "A6-partial-delivery")
    rendered = common.safe_format(
        release_gate.PROMPT,
        user_request=s["request"],
        deliverables="\n".join(f"{i}. {d}" for i, d in enumerate(s["deliverables"], 1)),
        mission=s["mission"], last_message=s["final"], transcript=s["final"],
        signals="python", git_status="M f.py", diff_hash="x", git_diff=s["diff"],
        proof=s["proof"], tool_log=s["tool_log"], loop_state="{}", lazy_impossible="False",
    )
    assert not re.search(r"\{(user_request|deliverables|mission|proof|tool_log|git_diff|transcript|last_message|signals|git_status|diff_hash|loop_state|lazy_impossible)\}", rendered)
    assert "1. Add the retry decorator" in rendered


# ---- the documented master switch actually disables everything --------------

@pytest.mark.parametrize("script", [
    "session_context.py", "compile_prompt.py", "capture_tool.py",
    "batch_feedback.py", "release_gate.py", "stop_failure.py",
])
def test_every_hook_honours_the_master_switch(script, tmp_path):
    # README calls OUTCOME_FUSION_ENABLED the "master switch for all hooks".
    # capture_tool, batch_feedback and stop_failure used to ignore it and keep
    # writing to the workspace, so the documented claim was false.
    src = (SCRIPTS / script).read_text(encoding="utf-8")
    assert 'env_bool("OUTCOME_FUSION_ENABLED"' in src, f"{script} ignores the master switch"

    env = dict(os.environ)
    env["OUTCOME_FUSION_ENABLED"] = "0"
    env.pop("DEEPSEEK_API_KEY", None)
    p = subprocess.run(
        [sys.executable, str(SCRIPTS / script)],
        input=json.dumps({"cwd": str(tmp_path), "session_id": "s-off", "prompt": "add a feature",
                          "tool_name": "Bash", "tool_input": {"command": "pytest -q"}}),
        capture_output=True, text=True, cwd=str(tmp_path), env=env, timeout=60,
    )
    assert p.returncode == 0
    assert p.stdout.strip() == "", f"{script} still emitted output while disabled"
    assert not (tmp_path / ".ai").exists(), f"{script} still wrote a workspace while disabled"


# ---- evidence QUALITY doctrine (added after the 38-scenario eval) -----------
#
# The first 38-scenario run caught 21/26 with 0 false blocks. All five misses
# scored 100 and shared one root cause: evidence was PRESENT, so the judge never
# asked whether the evidence actually established the claim. These lock the three
# rules added in response.

@pytest.mark.parametrize("needle", [
    "skipped",              # "3 passed, 12 skipped" is not covered
    "asserts nothing",      # a test that calls the function and checks nothing
    "flaky",                # passed only after reruns
    "defaults to off",      # shipped behind a disabled flag
])
def test_gate_doctrine_covers_defective_test_evidence(needle):
    assert needle in release_gate.SYSTEM.lower(), needle


@pytest.mark.parametrize("needle", [
    "credential, token, or key literal",
    "destructive or irreversible",
    "except exception: pass",
    "removal of a check, assertion, or test",
])
def test_gate_doctrine_reads_the_diff_for_danger(needle):
    assert needle in release_gate.SYSTEM.lower(), needle


@pytest.mark.parametrize("needle", [
    "look-ahead",
    "out-of-sample",
    "costs, fees, slippage",
    "survivorship",
])
def test_gate_doctrine_covers_quant_method_defects(needle):
    assert needle in release_gate.SYSTEM.lower(), needle


def test_evidence_lens_asks_what_was_not_covered():
    # The old lens ("is every important claim verified, sourced, tested?") is a
    # presence check and passed all five misses.
    lens = common.GATE_LENSES[1].lower()
    assert "evidence quality" in lens
    assert "not cover" in lens


def test_default_vote_count_still_uses_the_sharpened_lenses():
    # Adding the risk lens must not shuffle which lenses the default 3 votes use.
    lenses = common.vote_lenses(3)
    assert lenses[0] == ""
    assert "evidence quality" in lenses[1].lower()
    assert "completeness" in lenses[2].lower()


def test_risk_lens_is_available_at_higher_vote_counts():
    assert any("risk in the diff" in l.lower() for l in common.vote_lenses(6))


# ---- this repo is public: no private material may ship ----------------------

PRIVATE_MARKERS = [
    "c:\\users", "c:/users", "/home/mark",     # local absolute paths
    "msts-future", "msts-live", "edgelab", "0-dte-tasty",   # private repos
    "hydra", "calm-rich-iv",                                # private strategies
    "newgene", "@gmail",                                    # personal identifiers
    "references/",                                          # unshipped evidence files
]


@pytest.mark.parametrize("path", sorted(
    str(p.relative_to(PLUGIN)) for p in (PLUGIN / "skills").rglob("SKILL.md")
))
def test_shipped_skills_carry_no_private_material(path):
    # The quant skills were ported from the user's local ~/.claude/skills, which
    # reference private repos and dated P&L. The methodology ships; the evidence
    # and the machine paths do not.
    text = (PLUGIN / path).read_text(encoding="utf-8").lower()
    for marker in PRIVATE_MARKERS:
        assert marker not in text, f"{path} leaks private marker: {marker}"
    assert not re.search(r"sk-[A-Za-z0-9]{16,}", text), f"{path} contains a credential"


def test_ported_quant_skills_are_present_and_described():
    for name in ("bucket-brute-force", "quant-aggregation-integrity"):
        sk = PLUGIN / "skills" / name / "SKILL.md"
        assert sk.exists(), f"{name} not shipped"
        head = sk.read_text(encoding="utf-8")[:1200]
        assert head.lstrip().startswith("---") and "description:" in head, name


def test_no_dangling_reference_links_in_shipped_skills():
    # The source skill linked references/*.md that are deliberately not shipped.
    for sk in (PLUGIN / "skills").rglob("SKILL.md"):
        for link in re.findall(r"\]\((references/[^)]+)\)", sk.read_text(encoding="utf-8")):
            assert (sk.parent / link).exists(), f"{sk.name} links missing {link}"


# ---- secret scan: redaction blinds the judge, so detect locally -------------

SECRET_DIFF = '''+++ b/app/config.py
+ANALYTICS_TOKEN = "tok_live_9f2a71c4e5b8"
+requests.post(URL, headers={'Authorization': ANALYTICS_TOKEN})'''


def test_redaction_is_why_the_judge_cannot_see_a_committed_secret():
    # Documents the architectural cause: by the time the diff reaches the judge
    # the credential reads as already handled. Measured — the secret-in-diff
    # scenario was missed on every eval run, including after an explicit rule.
    assert "<REDACTED>" in common.redact(SECRET_DIFF)
    assert "tok_live_9f2a71c4e5b8" not in common.redact(SECRET_DIFF)


def test_scan_secrets_flags_added_credential_lines():
    findings = common.scan_secrets(SECRET_DIFF)
    assert findings, "credential literal not detected"
    assert findings[0].startswith("app/config.py:"), findings


def test_scan_secrets_never_echoes_the_secret_value():
    # The finding crosses the wire to a third-party judge; the value must not.
    for diff, secret in [
        (SECRET_DIFF, "tok_live_9f2a71c4e5b8"),
        ('+key = "sk-abcdefghijklmnopqrstuvwx"', "sk-abcdefghijklmnopqrstuvwx"),
        ('+token = "ghp_abcdefghijklmnopqrstuvwxyz12"', "ghp_abcdefghijklmnopqrstuvwxyz12"),
        ('+aws = "AKIAIOSFODNN7EXAMPLE"', "AKIAIOSFODNN7EXAMPLE"),
    ]:
        joined = " ".join(common.scan_secrets(diff))
        assert joined, f"missed: {diff}"
        assert secret not in joined, f"finding leaked the secret: {joined}"


def test_scan_secrets_ignores_removed_and_context_lines():
    assert common.scan_secrets('-API_KEY = "sk-abcdefghijklmnopqrst"') == []
    assert common.scan_secrets(' API_KEY = "sk-abcdefghijklmnopqrst"') == []
    assert common.scan_secrets("+++ b/config.py") == []  # header line only


def test_scan_secrets_quiet_on_a_clean_diff():
    assert common.scan_secrets("+def add(a, b):\n+    return a + b") == []
    assert common.scan_secrets('+token = os.environ["ANALYTICS_TOKEN"]') == []


def test_gate_prompt_and_doctrine_carry_the_scan():
    assert "{secret_scan}" in release_gate.PROMPT
    low = release_gate.SYSTEM.lower()
    assert "secret scan is authoritative" in low
    assert "rotate the exposed credential" in low


def test_heuristic_fallback_fails_closed_on_a_secret():
    # With no API key the gate used to return PASS, shipping the credential.
    review = release_gate.fallback_review("m", "proof", "log", False, ["added line 1: hardcoded key/token/password literal"])
    assert review["verdict"] == "FAIL"
    assert any("rotate" in a.lower() for a in review["next_actions"])


def test_git_status_and_diff_returns_findings(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cfg.py").write_text('API_KEY = "sk-abcdefghijklmnopqrstuv"\n', encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    (tmp_path / "cfg.py").write_text('API_KEY = "sk-abcdefghijklmnopqrstuv"\nTOKEN = "ghp_abcdefghijklmnopqrstuvwxyz12"\n', encoding="utf-8")

    status, diff, digest, secrets = common.git_status_and_diff(tmp_path)
    assert secrets, "secret in a real git diff was not detected"
    assert "ghp_abcdefghijklmnopqrstuvwxyz12" not in diff, "raw secret survived redaction"


def test_fixture_paths_are_marked_not_silently_blocking():
    # Without this, any repo that tests its own secret handling — including this
    # one — would fail its own gate on every run.
    app = common.scan_secrets('+++ b/app/config.py\n+API_KEY = "sk-abcdefghijklmnopqrstuv"')
    fixture = common.scan_secrets('+++ b/tests/test_auth.py\n+API_KEY = "sk-abcdefghijklmnopqrstuv"')
    assert app and "[test/fixture path" not in app[0]
    assert fixture and "[test/fixture path" in fixture[0]


def test_fallback_does_not_block_on_fixture_only_findings():
    review = release_gate.fallback_review(
        "m", "proof", "log", False,
        ["tests/test_auth.py:3: provider secret key (sk-...) [test/fixture path - confirm it is not a real credential]"],
    )
    assert review["verdict"] != "FAIL" or "credential literal" not in review["single_blocker"]


def test_run_argv_survives_pathspec_quoting_and_non_ascii(tmp_path):
    # shell=True uses cmd.exe on Windows, where a single quote is an ordinary
    # character, so ':(exclude).git' reached git with quotes attached and every
    # diff died with exit 128 — the judge got an error string instead of code.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "i"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("x = 2  # caf\u00e9 \u2014 na\u00efve \u2713\n", encoding="utf-8")

    status, diff, digest, secrets = common.git_status_and_diff(tmp_path)
    assert "@@" in diff, f"no real diff hunks: {diff[:200]}"
    assert "exit 128" not in diff and "returned non-zero" not in diff
    assert "x = 2" in diff


def test_run_cmd_keeps_the_failing_commands_own_output():
    out = common.run_cmd("git rev-parse --verify definitely-not-a-ref", pathlib.Path("."), timeout=15)
    assert "command failed" in out.lower()
    assert len(out.strip()) > len("[command failed: exit 128]"), "git's own message was discarded"


# ---- proof ledger signal-to-noise -------------------------------------------
#
# Measured on a real 160k-char ledger: auto-generated evidence stubs were 60% of
# blocks and 39% of the file, and inside the 30k the judge actually reads only 8
# real claims survived among 14 stubs. The plugin was diluting its own evidence.

def test_normalize_cmd_strips_the_shell_prologue():
    assert common.normalize_cmd('cd "C:/a b/repo" && pytest -q') == "pytest -q"
    assert common.normalize_cmd("cd /home/x/repo && ruff check .") == "ruff check ."
    assert common.normalize_cmd("cd 'C:/a b' && npm test") == "npm test"
    assert common.normalize_cmd("pytest -q") == "pytest -q"


def test_normalize_cmd_collapses_whitespace_and_bounds_length():
    assert common.normalize_cmd("pytest   -q\n  -x") == "pytest -q -x"
    assert len(common.normalize_cmd("x" * 500)) == 160


def test_dedup_now_matches_across_different_working_directories(tmp_path):
    # The `cd "<path>" &&` prefix made every invocation a unique string, so the
    # old dedup never fired on a repeated check run from a different shell.
    (tmp_path / "proof.md").write_text("- 10:00:00 check ran: `pytest -q` (output in tool_log.md)\n", encoding="utf-8")
    assert common.evidence_already_recorded(tmp_path, 'cd "C:/some/repo" && pytest -q')
    assert common.evidence_already_recorded(tmp_path, "cd /other/repo && pytest -q")
    assert not common.evidence_already_recorded(tmp_path, "ruff check .")


def test_dedup_scans_the_whole_ledger_not_just_the_tail(tmp_path):
    # Old limit was 6000 chars, so a check recorded early in a long session was
    # re-recorded every time it ran again.
    body = "- 10:00:00 check ran: `pytest -q` (output in tool_log.md)\n" + ("filler line\n" * 3000)
    (tmp_path / "proof.md").write_text(body, encoding="utf-8")
    assert len(body) > 30000
    assert common.evidence_already_recorded(tmp_path, "pytest -q")


def test_captured_check_is_one_compact_line(tmp_path):
    rc, _ = _run_hook(
        "capture_tool.py",
        {"cwd": str(tmp_path), "session_id": "s-cap", "hook_event_name": "PostToolUse",
         "tool_name": "Bash", "tool_input": {"command": 'cd "C:/repo" && pytest -q'},
         "tool_response": "2 passed"},
        tmp_path,
    )
    assert rc == 0
    proof = (tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_s-cap" / "proof.md").read_text(encoding="utf-8")
    entry = [ln for ln in proof.splitlines() if "check ran:" in ln]
    assert len(entry) == 1, proof
    assert "`pytest -q`" in entry[0], entry
    assert len(entry[0]) < 120, f"entry is not compact: {len(entry[0])} chars"
    # The old four-line stub restated boilerplate the judge already had.
    assert "Claim checked by command" not in proof
    assert "Remaining risk: Claude must interpret" not in proof


# ---- tool log framing -------------------------------------------------------
#
# Measured on 43 real sessions: a raw character tail started mid-entry in 43/43,
# so the first thing the judge read was always a fragment. Entry-aware framing
# shows 1.42x more whole entries in the same budget (5.0 -> 7.1 average).

def _log(n, size=300):
    return "".join(f"## 2026-08-{i+1:02d} 10:00:00 PostToolUse Bash\n" + ("x" * size) + "\n" for i in range(n))


def test_tail_tool_log_returns_whole_entries_only():
    out = common.tail_tool_log(_log(20), budget=2000)
    assert out.lstrip().startswith("## 2026-"), "output still begins mid-entry"
    assert len(out) <= 2000


def test_tail_tool_log_keeps_the_most_recent_entries():
    out = common.tail_tool_log(_log(20), budget=2000)
    assert "2026-08-20" in out, "newest entry missing"
    assert "2026-08-01" not in out, "kept the oldest instead of the newest"


def test_one_giant_entry_cannot_consume_the_whole_window():
    text = _log(5, size=200) + "## 2026-09-01 10:00:00 PostToolUse Bash\nSTART" + ("y" * 40000) + "END\n"
    out = common.tail_tool_log(text, budget=12000, per_entry=2500)
    assert "chars omitted" in out, "giant entry was not capped"
    assert out.count("## 2026-") >= 3, f"only {out.count('## 2026-')} entries survived a giant one"
    assert "START" in out and "END" in out, "head and tail of the capped entry must both survive"


def test_tail_tool_log_handles_a_log_with_no_entry_headers():
    assert common.tail_tool_log("no headers here", budget=100) == "no headers here"
    assert common.tail_tool_log("", budget=100) == ""


def test_single_entry_larger_than_the_budget_still_returns_something():
    out = common.tail_tool_log("## 2026-08-01 10:00:00 X\n" + ("z" * 50000), budget=1000, per_entry=900)
    assert out and len(out) <= 1000


def test_gate_uses_entry_aware_framing():
    src = (SCRIPTS / "release_gate.py").read_text(encoding="utf-8")
    assert "tail_tool_log(" in src
    assert "OUTCOME_FUSION_MAX_TOOLLOG_ENTRY_CHARS" in src


# ---- declined items are a result, not a gap ---------------------------------
#
# Live incident: the gate FAILed a turn because the assistant declined to write a
# plaintext API key to disk, and its next_actions told the assistant to "obtain
# the unredacted API key from the raw conversation" and write it anyway. A
# completeness gate that escalates against a safety boundary is worse than the
# work it is trying to enforce.

def test_doctrine_treats_a_stated_decline_as_closed():
    low = release_gate.SYSTEM.lower()
    assert "belong to the user" in low
    assert "declined" in low
    assert "authorization settles permission, not whether the action is the assistant's to take" in low


def test_doctrine_forbids_aiming_completeness_at_a_safety_boundary():
    low = release_gate.SYSTEM.lower()
    assert "never write next_actions that tell the assistant to reverse such a decision" in low
    assert "extract a secret" in low
    assert "must never be aimed at a safety boundary" in low


def test_doctrine_still_fails_ordinary_dodged_work():
    # The escape hatch must not become a way to skip hard work.
    low = release_gate.SYSTEM.lower()
    assert "too hard, tedious, or uncertain" in low
    assert "still `missing`, and still a fail" in low


def test_declined_item_is_not_reported_as_outstanding():
    msg = release_gate.terminal_review_message(
        {
            "verdict": "PASS",
            "progress_score": 90,
            "deliverables_status": [
                {"item": "Install the plugin", "status": "done"},
                {"item": "Save the API key to disk", "status": "declined",
                 "evidence": "handling a plaintext credential is the user's to perform"},
            ],
        },
        "PASS", "",
    )
    assert "Delivered: 2/2 requested items" in msg
    assert "1 declined" in msg
    assert "Outstanding" not in msg, msg


def test_declined_item_is_not_echoed_into_the_continue_prompt():
    review = {
        "verdict": "FAIL", "progress_score": 40,
        "deliverables_status": [
            {"item": "Save the API key to disk", "status": "declined", "evidence": "user's to perform"},
            {"item": "Write the docs", "status": "missing", "evidence": "not started"},
        ],
    }
    # The continue prompt is assembled inline in main(); assert on the filter
    # that decides which items get echoed back as pressure.
    src = (SCRIPTS / "release_gate.py").read_text(encoding="utf-8")
    assert "not in ('done', 'declined')" in src, "declined items still echoed as outstanding"
    outstanding = [d for d in review["deliverables_status"]
                   if str(d.get("status", "")).lower() not in ("done", "declined")]
    assert [d["item"] for d in outstanding] == ["Write the docs"]
