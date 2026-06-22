#!/usr/bin/env python3
from __future__ import annotations

import time
from common import cwd_from_hook, mirror_latest, read_stdin_json, safe_append, workspace_dir, redact


def main() -> int:
    payload = read_stdin_json()
    cwd = cwd_from_hook(payload)
    wdir = workspace_dir(cwd, payload)
    err = payload.get("error") or "unknown"
    detail = payload.get("error_details") or payload.get("last_assistant_message") or ""
    safe_append(wdir / "tool_log.md", f"\n\n## StopFailure {time.strftime('%Y-%m-%d %H:%M:%S')}\n{err}\n{redact(str(detail), limit=4000)}\n")
    mirror_latest(wdir, "tool_log.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
