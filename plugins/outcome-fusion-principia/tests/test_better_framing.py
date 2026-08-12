"""Behavioural tests for the "Better framing" feature.

The feature asks, before work starts, whether the user's request is the right
request — and is licensed to answer "None" when it already is.

The first tests written for it asserted that strings appear in ``TEMPLATE``.
That proves the instruction was authored, not that the feature does anything:
the section could be stripped by mission cleaning, never reach Claude, fire on
question turns, or take the whole mission down when the model omits it, and
every one of those string assertions would still pass.

These drive the real compile hook and assert observable behaviour.
"""
from __future__ import annotations

import json
import pathlib
import re

import common
import compile_prompt
import pytest
import release_gate

from test_hook_behaviour import drive  # shared in-process harness


FRAMED = (
    "# Mission\nMake the dashboard faster.\n\n"
    "# First principles decomposition\n1. Real objective: latency\n\n"
    "# Better framing\nGoal is a faster dashboard, not necessarily a cache. "
    "Alternatives: profile first and fix the dominant slow query; "
    "serve static assets from a CDN.\n\n"
    "# Deliverables checklist\n1. Make the dashboard faster\n"
)
UNFRAMED = "# Mission\nMake it faster.\n\n# Deliverables checklist\n1. Make it faster\n"
NONE_FRAMING = FRAMED.replace(
    "Goal is a faster dashboard, not necessarily a cache. "
    "Alternatives: profile first and fix the dominant slow query; "
    "serve static assets from a CDN.",
    "None - the request is the direct route.",
)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "plugin_data"))


def _compile(tmp_path, monkeypatch, prompt, returns, sid="fr"):
    """Run the real compile hook with a stubbed model; return what it produced."""
    calls = []
    queue = list(returns) if isinstance(returns, list) else None

    def model(system, body, **kw):
        calls.append((system, body))
        return queue.pop(0) if queue else returns

    rc, out = drive(compile_prompt, {"cwd": str(tmp_path), "session_id": sid, "prompt": prompt},
                    monkeypatch, compile_text=model)
    wdir = tmp_path / ".ai" / "outcome_fusion" / "sessions" / ("sid_" + sid)
    mission = (wdir / "mission.md").read_text(encoding="utf-8") if (wdir / "mission.md").exists() else ""
    return rc, out, mission, calls, wdir


# ---- prompt / reframe logic -------------------------------------------------

def _heading_pos(text: str, heading: str) -> int:
    """Index of an EXACT heading line, or -1.

    Substring matching is too loose here: mutation testing showed that renaming
    the section to "# Better framing REMOVED" still satisfied
    `"# Better framing" in body`, so the mutant survived and the feature could
    have been deleted from the template without a single test failing.
    """
    m = re.search(r"^" + re.escape(heading) + r"\s*$", text, re.M)
    return m.start() if m else -1


def test_the_model_is_actually_asked_for_a_better_framing(tmp_path, monkeypatch):
    _, _, _, calls, _ = _compile(tmp_path, monkeypatch, "add a caching layer", FRAMED)
    system, body = calls[0]
    assert _heading_pos(body, "# Better framing") >= 0, "the compiler never asks for a framing"
    # The heading alone is not the feature; the instruction has to be there too.
    assert "underlying goal" in body.lower(), "framing section carries no instruction"
    assert "none - the request is the direct route." in body.lower(), "no licence to decline"
    assert "question the request itself" in system.lower(), "system prompt does not license challenging the ask"


def test_framing_is_requested_before_scope_is_locked(tmp_path, monkeypatch):
    # Asked for after the checklist, an alternative would arrive once the
    # deliverables — and so the definition of done — were already fixed.
    _, _, _, calls, _ = _compile(tmp_path, monkeypatch, "add a caching layer", FRAMED)
    body = calls[0][1]
    framing = _heading_pos(body, "# Better framing")
    checklist = _heading_pos(body, "# Deliverables checklist")
    assert framing >= 0 and checklist >= 0
    assert framing < checklist


def test_framing_survives_mission_cleaning(tmp_path, monkeypatch):
    # clean_mission cuts everything before the first heading; a framing section
    # after "# Mission" must not be collateral damage.
    _, _, mission, _, _ = _compile(tmp_path, monkeypatch, "add a caching layer",
                                   "We need to think about this first.\n\n" + FRAMED)
    assert "# Better framing" in mission
    assert "not necessarily a cache" in mission
    assert "We need to think" not in mission


def test_the_framing_reaches_claude_not_just_the_file(tmp_path, monkeypatch):
    # The end-to-end point: the alternative must land in the context Claude
    # actually reads, or the feature changes nothing.
    _, out, _, _, _ = _compile(tmp_path, monkeypatch,
                               "add a caching layer so the dashboard loads faster", FRAMED)
    injected = json.dumps(out)
    assert "Better framing" in injected, "framing never reached Claude's context"
    assert "profile first" in injected, "the alternative itself was not delivered"


def test_a_none_framing_is_carried_through_unchanged(tmp_path, monkeypatch):
    # Restraint is a first-class outcome: "None" must survive verbatim, so a
    # well-posed request is not decorated with an invented alternative.
    _, out, mission, _, _ = _compile(tmp_path, monkeypatch, "run the tests", NONE_FRAMING)
    assert "None - the request is the direct route." in mission
    assert "None - the request is the direct route." in json.dumps(out)


def test_framing_does_not_become_a_deliverable(tmp_path, monkeypatch):
    # The checklist is what "done" is measured against. If the framing leaked
    # into it, Claude would be judged on adopting an alternative nobody asked for.
    _, _, mission, _, _ = _compile(tmp_path, monkeypatch, "add a caching layer", FRAMED)
    items = common.mission_deliverables(mission)
    assert items == ["Make the dashboard faster"], items
    assert not any("cache" in i.lower() or "profile" in i.lower() for i in items)


# ---- config / skip matrix ---------------------------------------------------

def test_question_turns_get_no_framing_because_they_get_no_mission(tmp_path, monkeypatch):
    called = []
    rc, out = drive(compile_prompt, {"cwd": str(tmp_path), "session_id": "fq",
                                     "prompt": "what does the release gate do?"}, monkeypatch,
                    compile_text=lambda *a, **k: called.append(1) or FRAMED)
    wdir = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_fq"
    assert not (wdir / "mission.md").exists()
    assert not called, "a question turn paid for a mission compile"
    assert "Better framing" not in json.dumps(out)


def test_disabling_the_plugin_removes_the_framing_entirely(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTCOME_FUSION_ENABLED", "0")
    called = []
    rc, out = drive(compile_prompt, {"cwd": str(tmp_path), "session_id": "fd", "prompt": "add caching"},
                    monkeypatch, compile_text=lambda *a, **k: called.append(1) or FRAMED)
    assert rc == 0 and out is None and not called


def test_offline_fallback_still_carries_a_framing_placeholder():
    # With no API the mission is the static template. It must still tell Claude
    # to speak up about a better route, or the feature vanishes precisely when
    # the compiler is unavailable.
    m = common.default_mission("add a caching layer", pathlib.Path("."))
    assert "# Better framing" in m
    assert "one sentence" in m.lower()


# ---- failure handling -------------------------------------------------------

def test_a_mission_without_a_framing_section_is_still_accepted(tmp_path, monkeypatch):
    # Framing is ADVISORY: an omitted advisory section must not trigger a retry
    # or a fallback. Gating the mission on it would make the feature mandatory.
    _, _, mission, calls, wdir = _compile(tmp_path, monkeypatch, "add caching", UNFRAMED, sid="fu")
    assert common.mission_is_usable(mission)
    assert "# Better framing" not in mission
    assert len(calls) == 1, "an omitted advisory section triggered a retry"
    assert not (wdir / "last_error.txt").exists()


def test_a_framing_without_a_checklist_is_not_a_usable_mission(tmp_path, monkeypatch):
    # The inverse: a model that answers the interesting part and skips the boring
    # one leaves the gate nothing to measure completeness against.
    framing_only = "# Mission\nx\n\n# Better framing\nGoal is speed, not caching.\n"
    _, _, mission, calls, wdir = _compile(tmp_path, monkeypatch, "add caching",
                                          [framing_only, framing_only], sid="fc")
    assert len(calls) == 2, "no retry on an unusable mission"
    assert common.mission_is_usable(mission), "fell through to an unusable mission"
    assert "no usable mission twice" in (wdir / "last_error.txt").read_text(encoding="utf-8")


def test_a_crashing_compiler_still_delivers_a_framing_placeholder(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("connection refused")

    rc, out = drive(compile_prompt, {"cwd": str(tmp_path), "session_id": "fx", "prompt": "add caching"},
                    monkeypatch, compile_text=boom)
    mission = (tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_fx" / "mission.md").read_text(encoding="utf-8")
    assert rc == 0, "a compiler crash must not kill the turn"
    assert "# Better framing" in mission


@pytest.mark.parametrize("garbage", ["", "   ", "not markdown at all", "# Better framing\nonly this\n"])
def test_malformed_compiler_output_never_reaches_claude_as_the_mission(tmp_path, monkeypatch, garbage):
    _, _, mission, _, _ = _compile(tmp_path, monkeypatch, "add caching", [garbage, garbage], sid="fg")
    assert common.mission_is_usable(mission)


def test_a_framing_containing_a_credential_is_redacted_before_it_travels(tmp_path, monkeypatch):
    # The framing text is echoed back to the judge inside the mission.
    leaky = FRAMED.replace("serve static assets from a CDN.",
                           'reuse the key API_KEY = "sk-abcdefghijklmnopqrst".')
    _, _, mission, _, _ = _compile(tmp_path, monkeypatch, "add caching", leaky, sid="fk")
    assert "sk-abcdefghijklmnopqrst" not in common.redact(mission)


# ---- the gate must never punish framing -------------------------------------

def test_framing_doctrine_forbids_failing_for_an_unadopted_alternative():
    low = release_gate.SYSTEM.lower()
    assert '"better framing" section is advisory' in low
    assert "never fail because no alternative was proposed" in low
    assert "non_blocking_followups, not in next_actions" in low


def test_an_unadopted_framing_is_not_reported_as_outstanding_work():
    msg = release_gate.terminal_review_message(
        {"verdict": "PASS", "progress_score": 95,
         "deliverables_status": [{"item": "Add caching", "status": "done"}],
         "closure_audit": {"non_blocking_followups": ["Profiling first might beat a cache"]}},
        "PASS", "")
    assert "Outstanding" not in msg, msg
