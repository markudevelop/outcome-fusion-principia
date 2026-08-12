"""Tests for the v0.7.0 Claude Opus 5 tuning.

Two sources drove these changes and they disagree in one place:

* Anthropic, "Prompting Claude Opus 5" — Opus 5 self-verifies, expands scope,
  narrates more, and delegates more readily. It says to REMOVE explicit
  verification / re-check instructions and legacy harness scaffolding that adds
  separate verification steps, and to cap subagent spawning.
* productcompass.pm, "How to Heal Claude Opus 5" — add "act don't ask",
  "a question is a question", and "done means done" blocks.

Resolution locked by these tests: the plugin keeps verification only where it is
OUT OF BAND (the DeepSeek release gate judging after the fact) and never as a
"check yourself again" instruction aimed at Claude.
"""
from __future__ import annotations

import importlib
import json
import os
import pathlib
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
        common.OPUS5_OPERATING_BLOCK,
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
def test_operating_block_covers_each_opus5_lever(needle):
    assert needle in common.OPUS5_OPERATING_BLOCK.lower()


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
    assert "Operating mode (tuned for Claude Opus 5)" in out

    # With no API key the gate falls back to the heuristic, which PASSes quietly.
    # Proof that it ran at all is the review it writes.
    rc, _ = _run_hook("release_gate.py", {**payload, "last_assistant_message": "Done."}, tmp_path)
    assert rc == 0
    assert (wdir / "review.md").exists(), "gate must still judge a build turn"
