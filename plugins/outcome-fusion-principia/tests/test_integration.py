"""Integration tests: the whole plugin is internally consistent and the hooks
work together end to end.

The pipeline test runs each hook script as a subprocess with NO API key, so
every DeepSeek call falls back to the built-in heuristic. That makes it
deterministic and CI-safe while still exercising the real scripts, the real
manifest wiring, and the shared session workspace they all read and write.
"""
from __future__ import annotations
import json
import os
import pathlib
import py_compile
import re
import subprocess
import sys

PLUGIN = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = PLUGIN / "scripts"
MANIFEST = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))

# The hook events Claude Code actually supports (subset we rely on).
VALID_HOOK_EVENTS = {
    "SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
    "PostToolUseFailure", "PostToolBatch", "Stop", "StopFailure",
    "SubagentStart", "SubagentStop", "Notification", "SessionEnd", "PreCompact",
}


# ---- structural consistency -------------------------------------------------

def test_manifest_command_files_exist():
    for c in MANIFEST["commands"]:
        assert (PLUGIN / c.lstrip("./")).exists(), f"missing command: {c}"


def test_manifest_agents_exist_with_frontmatter():
    for a in MANIFEST["agents"]:
        p = PLUGIN / a.lstrip("./")
        assert p.exists(), f"missing agent: {a}"
        txt = p.read_text(encoding="utf-8")
        assert txt.lstrip().startswith("---"), f"no frontmatter: {a}"
        assert "name:" in txt and "description:" in txt, f"incomplete frontmatter: {a}"


def test_every_skill_has_description():
    subs = [d for d in (PLUGIN / "skills").iterdir() if d.is_dir()]
    assert subs, "no skills found"
    for d in subs:
        sk = d / "SKILL.md"
        assert sk.exists(), f"{d.name} has no SKILL.md"
        assert "description:" in sk.read_text(encoding="utf-8"), d.name


def test_hooks_reference_existing_scripts_and_valid_events():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    for event, blocks in hooks["hooks"].items():
        assert event in VALID_HOOK_EVENTS, f"unknown hook event: {event}"
        for block in blocks:
            for h in block["hooks"]:
                m = re.search(r"scripts/(\w+\.py)", h["command"])
                assert m, f"hook command has no script: {h['command']}"
                assert (SCRIPTS / m.group(1)).exists(), f"missing script: {m.group(1)}"


def test_all_scripts_compile():
    for f in SCRIPTS.glob("*.py"):
        py_compile.compile(str(f), doraise=True)


# ---- behavioural end-to-end pipeline (offline, heuristic fallback) ----------

def _run_hook(script: str, payload: dict, cwd: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["OUTCOME_FUSION_ENABLED"] = "1"
    for k in ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        env.pop(k, None)  # force the offline fallback path
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script)],
        input=json.dumps(payload), text=True, capture_output=True,
        # The hooks emit UTF-8 bytes; decode as UTF-8 so the reader thread never
        # hits a cp1252 UnicodeDecodeError on Windows.
        encoding="utf-8", errors="replace",
        cwd=str(SCRIPTS), env=env, timeout=60,
    )


def test_hook_pipeline_works_together(tmp_path):
    cwd = str(tmp_path).replace("\\", "/")
    ws = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_itest"
    base = {"cwd": cwd, "session_id": "itest", "transcript_path": ""}

    # 1) prompt submitted -> mission compiled (fallback) and written
    r = _run_hook("compile_prompt.py", {**base, "hook_event_name": "UserPromptSubmit",
                                        "prompt": "add a function and test it"}, cwd)
    assert r.returncode == 0, r.stderr
    assert (ws / "mission.md").exists()
    assert (ws / "proof.md").exists()

    # 2) a verification command -> recorded in tool log + proof ledger
    r = _run_hook("capture_tool.py", {**base, "hook_event_name": "PostToolUse",
                                      "tool_name": "Bash", "tool_input": {"command": "pytest -q"},
                                      "tool_response": "2 passed"}, cwd)
    assert r.returncode == 0, r.stderr
    assert (ws / "tool_log.md").exists()

    # 3) session start can reload the same workspace it created
    r = _run_hook("session_context.py", {**base, "hook_event_name": "SessionStart",
                                         "source": "resume"}, cwd)
    assert r.returncode == 0, r.stderr

    # 4) stop -> release gate produces a verdict (heuristic fallback) in review.md
    r = _run_hook("release_gate.py", {**base, "hook_event_name": "Stop",
                                      "last_assistant_message": "Implemented and verified, all green."}, cwd)
    assert r.returncode == 0, r.stderr
    review = (ws / "review.md").read_text(encoding="utf-8")
    assert '"verdict"' in review


def test_release_gate_autocontinue_blocks_on_fail(tmp_path):
    # Offline -> heuristic FAIL (lazy refusal). With autocontinue on (default),
    # the Stop hook must emit decision: block to force Claude to keep working.
    # CLAUDE_PLUGIN_DATA is redirected so the continuation counter starts fresh.
    cwd = str(tmp_path).replace("\\", "/")
    ws = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_itest"
    ws.mkdir(parents=True)
    (ws / "mission.md").write_text("# Mission\nDo the thing.\n", encoding="utf-8")
    (ws / "proof.md").write_text("# Proof\n", encoding="utf-8")
    payload = {"cwd": cwd, "session_id": "itest", "transcript_path": "",
               "hook_event_name": "Stop",
               "last_assistant_message": "This is impossible, it cannot be done."}
    env_extra = {"CLAUDE_PLUGIN_DATA": str(tmp_path / "pdata"), "OUTCOME_FUSION_AUTOCONTINUE": "1"}
    r = _run_hook("release_gate.py", payload, cwd, env_extra)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout).get("decision") == "block"

    # With autocontinue off, the same FAIL must NOT block (guidance only).
    env_extra["OUTCOME_FUSION_AUTOCONTINUE"] = "0"
    r = _run_hook("release_gate.py", payload, cwd, env_extra)
    out = json.loads(r.stdout)
    assert out.get("decision") is None
    assert out["hookSpecificOutput"]["additionalContext"]


def test_capture_tool_dedups_repeated_evidence(tmp_path):
    cwd = str(tmp_path).replace("\\", "/")
    ws = tmp_path / ".ai" / "outcome_fusion" / "sessions" / "sid_itest"
    payload = {"cwd": cwd, "session_id": "itest", "transcript_path": "",
               "hook_event_name": "PostToolUse", "tool_name": "Bash",
               "tool_input": {"command": "pytest -q"}, "tool_response": "ok"}
    for _ in range(3):
        assert _run_hook("capture_tool.py", payload, cwd).returncode == 0
    proof = (ws / "proof.md").read_text(encoding="utf-8")
    assert proof.count("Claim checked by command: `pytest -q`") == 1
