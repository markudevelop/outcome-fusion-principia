#!/usr/bin/env python3
from __future__ import annotations

from common import (
    combined_memory,
    cwd_from_hook,
    env_bool,
    find_resume_workspace,
    json_stdout,
    mirror_latest,
    read_stdin_json,
    safe_read,
    safe_write,
    session_paths_block,
    workspace_dir,
    workspace_root_dir,
)


def main() -> int:
    payload = read_stdin_json()
    if not env_bool("OUTCOME_FUSION_ENABLED", True):
        return 0

    cwd = cwd_from_hook(payload)
    source = str(payload.get("source") or payload.get("matcher") or "").lower()
    wdir = workspace_dir(cwd, payload)

    # On /resume, prefer the existing session workspace if Claude gives us enough identity to find it.
    # If Claude changes session_id but keeps transcript_path, this still reconnects.
    if source == "resume" and not (wdir / "mission.md").exists():
        found = find_resume_workspace(cwd, payload)
        if found is not None:
            wdir = found
            safe_write(workspace_root_dir(cwd) / "current_session.txt", wdir.name)

    if not (wdir / "proof.md").exists():
        safe_write(wdir / "proof.md", "# Proof ledger\n\nRecord every important claim as: claim, evidence, method, result, confidence, remaining risk.\n")
        mirror_latest(wdir, "proof.md")

    memory = combined_memory(wdir, limit=16000)
    mission = safe_read(wdir / "mission.md", limit=16000)
    review = safe_read(wdir / "review.md", limit=12000)
    closure = safe_read(wdir / "closure.md", limit=12000)

    if not memory and not mission and source != "resume":
        return 0

    context = f"""
Outcome Fusion Principia session context loaded.

{session_paths_block(wdir)}

Resume behavior:
This is a session-scoped workspace. If this Claude conversation is resumed, continue using these exact files instead of creating global `.ai/outcome_fusion/*.md` files.

Current mission preview:
{mission[:9000]}

Last review preview:
{review[:5000]}

Closure preview:
{closure[:5000]}

Project/session memory preview:
{memory[:9000]}

Keep using first principles, simplification, verification, and release readiness. Update the session proof ledger, not a global proof file.
""".strip()

    json_stdout({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context
        },
        "suppressOutput": True,
        "systemMessage": f"Outcome Fusion context loaded for session {wdir.name}."
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
