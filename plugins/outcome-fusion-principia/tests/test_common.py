"""Unit tests for the pure helpers in common.py."""
import json

import common


def test_safe_format_substitutes_named_tokens_and_leaves_braces():
    tpl = 'Value {x} and json {"k": 1}'
    out = common.safe_format(tpl, x="HELLO")
    assert out == 'Value HELLO and json {"k": 1}'


def test_safe_format_does_not_raise_on_literal_json_braces():
    # str.format would raise KeyError here; safe_format must not.
    out = common.safe_format('{a} -> {"verdict": "PASS"}', a="ok")
    assert out == 'ok -> {"verdict": "PASS"}'


def test_contains_lazy_impossible_detects_refusals():
    assert common.contains_lazy_impossible("This is impossible")
    assert common.contains_lazy_impossible("we cannot do this")
    assert common.contains_lazy_impossible("there is no way to ship it")


def test_contains_lazy_impossible_ignores_normal_completion():
    assert not common.contains_lazy_impossible("Implemented and verified, all green.")
    assert not common.contains_lazy_impossible("")
    assert common.contains_lazy_impossible("It won't work in this framework.")


def test_contains_lazy_impossible_no_false_positive_when_quoting_or_discussing():
    # Every one of these tripped the gate during development; none is a refusal.
    false_positives = [
        'The scenario row "This is impossible, cannot be done" was a test input.',  # quoted
        "The gate flags the word `impossible` in prose.",                            # inline code
        "Never say impossible without proof.",                                       # rule text
        "Do not say cannot unless reduced to a blocker.",                            # rule text
        "| B3 | This is impossible, cannot be done | FAIL |",                        # table cell
    ]
    flagged = [t for t in false_positives if common.contains_lazy_impossible(t)]
    assert flagged == [], f"false positives still firing: {flagged}"


def test_append_memory_dedups(tmp_path):
    common.append_memory(tmp_path, "Always verify before claiming done.")
    common.append_memory(tmp_path, "Always verify before claiming done.")
    common.append_memory(tmp_path, "A different lesson.")
    body = (tmp_path / "memory.md").read_text(encoding="utf-8")
    assert body.count("Always verify before claiming done.") == 1
    assert "A different lesson." in body


def test_should_skip_prompt():
    assert common.should_skip_prompt("")
    assert common.should_skip_prompt("/help")
    assert common.should_skip_prompt("do this nofusion")
    assert not common.should_skip_prompt("/outcome-fusion run")
    assert not common.should_skip_prompt("build the thing")


def test_redact_secrets():
    assert "<REDACTED>" in common.redact("api_key=sk-abcdefabcdef123456")
    assert "Bearer <REDACTED>" in common.redact("Authorization: Bearer abc.def.ghi")
    assert "sk-<REDACTED>" in common.redact("token sk-ABCDEFGHIJKLMNOPqrstuv")


def test_parse_json_loose_extracts_embedded_object():
    assert common.parse_json_loose('prefix {"a": 1} suffix') == {"a": 1}
    assert common.parse_json_loose("not json at all") == {}


def test_parse_json_loose_handles_reasoning_preamble_with_stray_brace():
    # Real failure mode: a reasoning preamble containing a stray "{", then the
    # actual JSON answer. The old greedy regex started at the stray brace and
    # failed; the answer object must still be recovered.
    raw = (
        'We need to evaluate. The proof says "claim: {10x}" but no benchmark.\n'
        'Therefore:\n'
        '{\n  "verdict": "FAIL",\n  "progress_score": 20\n}'
    )
    out = common.parse_json_loose(raw)
    assert out.get("verdict") == "FAIL"
    assert out.get("progress_score") == 20


def test_parse_json_loose_braces_inside_strings():
    assert common.parse_json_loose('{"note": "use {x} here", "ok": true}') == {
        "note": "use {x} here",
        "ok": True,
    }


def test_env_bool(monkeypatch):
    monkeypatch.setenv("OF_TEST_FLAG", "0")
    assert common.env_bool("OF_TEST_FLAG", True) is False
    monkeypatch.setenv("OF_TEST_FLAG", "off")
    assert common.env_bool("OF_TEST_FLAG", True) is False
    monkeypatch.delenv("OF_TEST_FLAG", raising=False)
    assert common.env_bool("OF_TEST_FLAG", True) is True


def test_env_int(monkeypatch):
    monkeypatch.setenv("OF_TEST_INT", "7")
    assert common.env_int("OF_TEST_INT", 1) == 7
    monkeypatch.setenv("OF_TEST_INT", "notanint")
    assert common.env_int("OF_TEST_INT", 3) == 3


def test_call_deepseek_json_retries_on_unparseable(monkeypatch):
    calls = {"n": 0}

    def fake(system, user, **kw):
        calls["n"] += 1
        return "garbage, not json" if calls["n"] == 1 else '{"verdict": "PASS", "progress_score": 90}'

    monkeypatch.setattr(common, "call_deepseek", fake)
    data, raw = common.call_deepseek_json("sys", "user", require_keys=["verdict"])
    assert data.get("verdict") == "PASS"
    assert calls["n"] == 2  # recovered on the second, stricter attempt


def test_call_deepseek_json_no_retry_when_first_parses(monkeypatch):
    calls = {"n": 0}

    def fake(system, user, **kw):
        calls["n"] += 1
        return '{"verdict": "FAIL", "progress_score": 10}'

    monkeypatch.setattr(common, "call_deepseek", fake)
    data, _ = common.call_deepseek_json("s", "u", require_keys=["verdict"])
    assert data["verdict"] == "FAIL"
    assert calls["n"] == 1  # no wasted call in the common case


def test_parse_json_loose_handles_markdown_fence():
    raw = '```json\n{"verdict": "PASS", "n": 3}\n```'
    assert common.parse_json_loose(raw) == {"verdict": "PASS", "n": 3}


def test_parse_json_loose_returns_last_object_after_reasoning():
    raw = 'first {"draft": true} then final answer {"verdict": "FAIL"}'
    # Both parse; the last (final) object should win.
    assert common.parse_json_loose(raw) == {"verdict": "FAIL"}


def test_balanced_json_spans_counts_nested_and_multiple():
    spans = common._balanced_json_spans('a {"x": {"y": 1}} b {"z": 2}')
    assert len(spans) == 2


def test_redact_private_key_block():
    raw = "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----"
    assert "PRIVATE_KEY_REDACTED" in common.redact(raw)
    assert "ghp_<REDACTED>" not in common.redact("clean text")


def test_session_key_transcript_fallback_when_no_session_id(tmp_path):
    key = common.session_key_from_payload({"transcript_path": "/x/y.jsonl"}, tmp_path)
    assert key.startswith("tx_")


def test_call_deepseek_json_returns_empty_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr(common, "call_deepseek", lambda *a, **k: "never json")
    data, raw = common.call_deepseek_json("s", "u", require_keys=["verdict"])
    assert data == {}
    assert raw == "never json"


def test_aggregate_reviews_empty_returns_empty():
    assert common.aggregate_reviews([]) == {}
    assert common.aggregate_reviews([{"no_verdict": 1}]) == {}


def test_aggregate_reviews_averages_score():
    out = common.aggregate_reviews([
        {"verdict": "PASS", "progress_score": 100},
        {"verdict": "PASS", "progress_score": 80},
    ])
    assert out["progress_score"] == 90


def test_summarize_metrics(tmp_path):
    (tmp_path / "metrics.jsonl").write_text(
        '{"label": "release_gate", "input_tokens": 100, "output_tokens": 50, "latency_ms": 1000}\n'
        '{"label": "mission_compile", "input_tokens": 200, "output_tokens": 30, "latency_ms": 3000}\n',
        encoding="utf-8",
    )
    m = common.summarize_metrics(tmp_path)
    assert m["calls"] == 2
    assert m["total_tokens"] == 380
    assert m["avg_latency_ms"] == 2000
    assert m["by_label"] == {"release_gate": 1, "mission_compile": 1}


def test_summarize_metrics_empty(tmp_path):
    m = common.summarize_metrics(tmp_path)
    assert m["calls"] == 0 and m["total_tokens"] == 0


def test_evidence_already_recorded(tmp_path):
    assert not common.evidence_already_recorded(tmp_path, "pytest -q")
    (tmp_path / "proof.md").write_text("## Evidence\nClaim checked by command: `pytest -q`\n", encoding="utf-8")
    assert common.evidence_already_recorded(tmp_path, "pytest -q")
    assert not common.evidence_already_recorded(tmp_path, "ruff check .")


def test_json_stdout_handles_unicode_without_crashing(capfd):
    # Regression: a non-ASCII char (an arrow) used to crash the hook on Windows
    # cp1252 stdout. Output must stay valid JSON and round-trip the character.
    common.json_stdout({"systemMessage": "arrow ↔ ok"})
    out = capfd.readouterr().out
    assert json.loads(out)["systemMessage"] == "arrow ↔ ok"


def test_vote_lenses_are_distinct_and_cycle():
    assert common.vote_lenses(1) == [""]
    three = common.vote_lenses(3)
    assert len(three) == 3
    assert three[0] == ""  # first vote keeps the full doctrine
    assert len({x for x in three}) == 3  # distinct perspectives
    assert any("EVIDENCE" in x for x in three)
    assert len(common.vote_lenses(7)) == 7  # cycles past the lens list


def test_aggregate_reviews_single_passthrough():
    r = {"verdict": "PASS", "progress_score": 90}
    assert common.aggregate_reviews([r]) == r


def test_aggregate_reviews_majority_pass():
    out = common.aggregate_reviews([
        {"verdict": "PASS", "progress_score": 90},
        {"verdict": "PASS", "progress_score": 80},
        {"verdict": "FAIL", "progress_score": 30},
    ])
    assert out["verdict"] == "PASS"
    assert out["votes"] == {"PASS": 2, "FAIL": 1}


def test_aggregate_reviews_split_is_conservative_fail():
    out = common.aggregate_reviews([
        {"verdict": "PASS"}, {"verdict": "FAIL"}, {"verdict": "FAIL"},
    ])
    assert out["verdict"] == "FAIL"


def test_aggregate_reviews_blocked_without_pass_majority():
    out = common.aggregate_reviews([
        {"verdict": "BLOCKED"}, {"verdict": "FAIL"}, {"verdict": "PASS"},
    ])
    assert out["verdict"] == "BLOCKED"


def test_aggregate_reviews_unions_next_actions():
    out = common.aggregate_reviews([
        {"verdict": "FAIL", "next_actions": ["a", "b"]},
        {"verdict": "FAIL", "next_actions": ["b", "c"]},
    ])
    assert out["next_actions"] == ["a", "b", "c"]


def test_session_key_is_stable_and_prefixed(tmp_path):
    key1 = common.session_key_from_payload({"session_id": "abc-123"}, tmp_path)
    key2 = common.session_key_from_payload({"session_id": "abc-123"}, tmp_path)
    assert key1 == key2
    assert key1.startswith("sid_")
