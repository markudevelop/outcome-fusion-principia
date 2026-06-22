"""Unit tests for the pure helpers in common.py."""
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


def test_session_key_is_stable_and_prefixed(tmp_path):
    key1 = common.session_key_from_payload({"session_id": "abc-123"}, tmp_path)
    key2 = common.session_key_from_payload({"session_id": "abc-123"}, tmp_path)
    assert key1 == key2
    assert key1.startswith("sid_")
