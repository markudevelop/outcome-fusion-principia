#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
from common import cwd_from_hook, env_bool, evidence_already_recorded, json_stdout, mirror_latest, read_stdin_json, safe_append, summarize_hook_tool, workspace_dir

CHECK_HINTS = re.compile(r"\b(test|pytest|vitest|jest|playwright|cypress|lint|typecheck|tsc|mypy|ruff|eslint|build|cargo test|go test|backtest|benchmark)\b", re.I)


def main() -> int:
    payload = read_stdin_json()
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
        safe_append(
            wdir / "proof.md",
            f"\n\n## Evidence {time.strftime('%Y-%m-%d %H:%M:%S')}\nClaim checked by command: `{cmd}`\nResult: see the session `tool_log.md` latest entry.\nRemaining risk: Claude must interpret the result and update this ledger if it proves or disproves a claim.\n"
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
