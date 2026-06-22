"""Regression tests that lock the v0.3.7 fixes.

These guard the two bugs that silently disabled the release gate in every
session: the unescaped-JSON-brace KeyError, and the always-true lazy detector.
"""
import common
import compile_prompt
import pytest
import release_gate

GATE_FIELDS = dict(
    mission="M", last_message="L", transcript="T", signals="S",
    git_status="GS", diff_hash="DH", git_diff="GD", proof="P",
    tool_log="TL", loop_state="{}", lazy_impossible="False",
)


def test_release_gate_prompt_embeds_json_schema():
    # The schema block is why the original str.format crashed.
    assert '"verdict"' in release_gate.PROMPT


def test_original_str_format_would_raise_keyerror():
    # Documents the exact bug that was fixed.
    with pytest.raises(KeyError):
        release_gate.PROMPT.format(**GATE_FIELDS)


def test_safe_format_renders_gate_prompt_without_error():
    out = common.safe_format(release_gate.PROMPT, **GATE_FIELDS)
    assert "MISSION:\nM" in out          # named token substituted
    assert '"verdict"' in out            # JSON schema preserved intact
    assert "{mission}" not in out        # no leftover placeholders


def test_compile_template_renders():
    out = compile_prompt.TEMPLATE.format(
        prompt="p", previous_mission="pm", memory="mem", signals="sig"
    )
    assert "p" in out and "{prompt}" not in out


def test_is_anything_else_query():
    assert compile_prompt.is_anything_else_query("anything else?")
    assert compile_prompt.is_anything_else_query("did you miss anything")
    assert not compile_prompt.is_anything_else_query("build the feature")


def test_default_mission_is_self_contained(tmp_path):
    # Fallback used when DeepSeek is unreachable must still be a usable mission.
    text = common.default_mission("make it fast", tmp_path)
    assert text.startswith("# Mission")
    assert "make it fast" in text
