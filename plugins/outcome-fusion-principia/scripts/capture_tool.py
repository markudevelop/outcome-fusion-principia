#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
from common import cwd_from_hook, env_bool, evidence_already_recorded, json_stdout, mirror_latest, normalize_cmd, read_stdin_json, safe_append, summarize_hook_tool, workspace_dir

CHECK_HINTS = re.compile(r"\b(test|pytest|vitest|jest|playwright|cypress|lint|typecheck|tsc|mypy|ruff|eslint|build|cargo test|go test|backtest|benchmark)\b", re.I)


def main() -> int:
    payload = read_stdin_json()
    if not env_bool("OUTCOME_FUSION_ENABLED", True):
        return 0
    if not env_bool("OUTCOME_FUSION_CAPTURE_ENABLED", True):
        return 0
    cwd = cwd_from_hook(payload)
    wdir = workspace_dir(cwd, payload)
    event = payload.get("hook_event_name") or ""
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    cmd = ""
    if isinstance(tool_input, dict):
        cmd = str(tool_input.get("command") or tool_input.get("file_path") or tool_input.get("pattern") or "")

    summary = summarize_hook_tool(payload, limit=9000)
    safe_append(wdir / "tool_log.md", f"\n\n## {time.strftime('%Y-%m-%d %H:%M:%S')} {event} {tool}\n```text\n{summary}\n```\n")
    mirror_latest(wdir, "tool_log.md")

    context = ""
    if event == "PostToolUseFailure":
        context = "Outcome Fusion noticed this tool failed. Do not repeat the same failing action blindly. Identify why it failed, change the hypothesis, then run the smallest next check."
    elif tool == "Bash" and CHECK_HINTS.search(cmd) and not evidence_already_recorded(wdir, cmd):
        # One compact line, not a four-line stub. The old block restated the
        # command, pointed at tool_log.md for the result, and repeated
        # boilerplate about interpreting it — ~900 chars carrying no evidence,
        # while the judge only reads the ledger's last 30k. Measured on a real
        # 160k ledger: these stubs were 60% of blocks and 39% of the file, and
        # inside the judge's window only 8 real claims survived among 14 stubs.
        # The useful half of this hook was always the nudge below.
        safe_append(
            wdir / "proof.md",
            f"\n- {time.strftime('%H:%M:%S')} check ran: `{normalize_cmd(cmd)}` (output in tool_log.md)"
        )
        mirror_latest(wdir, "proof.md")
        context = "Outcome Fusion recorded this verification command in the session proof ledger. Interpret the result and update claim, evidence, method, confidence, and remaining risk if needed."

    if context:
        out = {
            "hookSpecificOutput": {
                "hookEventName": event,
                "additionalContext": context
            },
            "suppressOutput": True
        }
        if env_bool("OUTCOME_FUSION_TERMINAL_LOG", True):
            if event == "PostToolUseFailure":
                out["systemMessage"] = "Outcome Fusion: tool failed. Claude will change strategy instead of repeating blindly."
            elif tool == "Bash" and CHECK_HINTS.search(cmd):
                out["systemMessage"] = f"Outcome Fusion: verification command recorded: {cmd[:160]}"
        json_stdout(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
