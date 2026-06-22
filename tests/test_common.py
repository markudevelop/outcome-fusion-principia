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


def test_session_key_is_stable_and_prefixed(tmp_path):
    key1 = common.session_key_from_payload({"session_id": "abc-123"}, tmp_path)
    key2 = common.session_key_from_payload({"session_id": "abc-123"}, tmp_path)
    assert key1 == key2
    assert key1.startswith("sid_")
