#!/usr/bin/env python3
from __future__ import annotations

from common import cwd_from_hook, env_bool, mirror_latest, read_stdin_json, safe_append, workspace_dir


def main() -> int:
    payload = read_stdin_json()
    if not env_bool("OUTCOME_FUSION_BATCH_HINTS", True):
        return 0
    calls = payload.get("tool_calls") or []
    if not calls or len(calls) < 2:
        return 0
    cwd = cwd_from_hook(payload)
    wdir = workspace_dir(cwd, payload)
    tools = [str(c.get("tool_name") or "") for c in calls if isinstance(c, dict)]
    safe_append(wdir / "tool_log.md", f"\n\n## PostToolBatch\nTools: {', '.join(tools)}\n")
    mirror_latest(wdir, "tool_log.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
