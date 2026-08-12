#!/usr/bin/env python3
"""A/B the gate's payload caps on REAL session workspaces.

Why this exists
---------------
v0.7.0 cut what the release gate sends the judge (proof 50k->30k chars, tool log
50k->12k, transcript 50k->20k, diff 100k->40k). That was shipped as a pure cost
change with an explicitly UNMEASURED effect on verdict quality, which is exactly
the kind of unsupported claim this plugin exists to refuse.

`run_eval.py` cannot settle it: its scenarios are a few hundred characters, so no
cap ever engages. The caps only bite on long real sessions. So this harness
replays actual `.ai/outcome_fusion/sessions/*` workspaces through the shipped
gate twice — once at the pre-0.7.0 limits, once at the current ones — and asks
one question:

    Does the smaller payload change the verdict?

Agreement means the truncated context carried the same decision. Disagreement,
and in which direction, is the real cost of the saving.

Run
---
    export DEEPSEEK_API_KEY=...
    python plugins/outcome-fusion-principia/eval/ab_payload_caps.py --n 10
    python plugins/outcome-fusion-principia/eval/ab_payload_caps.py --root /path/to/repo
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

PLUGIN = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN / "scripts"))
import common  # noqa: E402
import release_gate as rg  # noqa: E402

# (proof, tool_log, transcript, diff) in characters.
OLD_CAPS = dict(proof=50000, tool_log=50000, label="pre-0.7.0")
NEW_CAPS = dict(proof=30000, tool_log=12000, label="0.7.0")


def build_prompt(wdir: pathlib.Path, caps: dict) -> str:
    mission = common.safe_read(wdir / "mission.md", limit=50000)
    proof = common.safe_read(wdir / "proof.md", limit=caps["proof"])
    tool_log = common.safe_read(wdir / "tool_log.md", limit=caps["tool_log"])
    request = common.safe_read(wdir / "request.txt", limit=8000).strip() or "(not recorded)"
    deliverables = common.mission_deliverables(mission)
    return common.safe_format(
        rg.PROMPT,
        user_request=request,
        deliverables=("\n".join(f"{i}. {d}" for i, d in enumerate(deliverables, 1))
                      if deliverables else "(none enumerated - judge completeness against the verbatim request)"),
        mission=mission,
        last_message="(replayed from the session workspace; final message not retained)",
        transcript="(not retained in the workspace)",
        signals="replayed session",
        git_status="(not retained)",
        diff_hash="replay",
        git_diff="(not retained)",
        proof=proof,
        tool_log=tool_log,
        loop_state=json.dumps({"forced_continuations": 0, "same_diff_count": 0, "max_continues": 5}),
        lazy_impossible="False",
        secret_scan="(no credential patterns matched)",
    )


def judge(prompt: str) -> tuple[str, object]:
    data, _ = common.call_deepseek_json(
        rg.SYSTEM, prompt, max_tokens=4200, temperature=0.1, timeout=170, require_keys=["verdict"]
    )
    return str(data.get("verdict", "?")).upper(), data.get("progress_score", "?")


def pick_sessions(root: pathlib.Path, n: int) -> list[pathlib.Path]:
    """Sessions where the new caps actually truncate — the only informative ones."""
    out = []
    for s in sorted(root.iterdir()) if root.exists() else []:
        if not s.is_dir() or not (s / "mission.md").exists():
            continue
        size = lambda f: f.stat().st_size if f.exists() else 0  # noqa: E731
        if size(s / "proof.md") > NEW_CAPS["proof"] or size(s / "tool_log.md") > NEW_CAPS["tool_log"]:
            out.append((size(s / "proof.md") + size(s / "tool_log.md"), s))
    out.sort(reverse=True, key=lambda x: x[0])
    return [s for _, s in out[:n]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="repo containing .ai/outcome_fusion/sessions")
    ap.add_argument("--n", type=int, default=8, help="how many sessions to replay")
    ap.add_argument("--control", action="store_true",
                    help="NOISE FLOOR: judge each session twice at the SAME caps. "
                         "Without this the A/B is uninterpretable — judge verdicts are "
                         "stochastic, so some disagreement is noise, not the caps.")
    args = ap.parse_args()

    sessions_root = pathlib.Path(args.root).resolve() / ".ai" / "outcome_fusion" / "sessions"
    sessions = pick_sessions(sessions_root, args.n)
    if not sessions:
        print(f"No sessions under {sessions_root} large enough for the caps to bite.")
        return 1

    # In control mode both arms use the CURRENT caps, so any disagreement is
    # judge noise rather than an effect of the payload size.
    caps_a = NEW_CAPS if args.control else OLD_CAPS
    label_a = "0.7.0 run A" if args.control else "pre-0.7.0"
    label_b = "0.7.0 run B" if args.control else "0.7.0"
    mode = "NOISE FLOOR (same caps twice)" if args.control else "A/B (old caps vs new caps)"

    print(f"{mode}: {len(sessions)} real sessions through the shipped gate.")
    print(f"{'session':26} {label_a:>13} {label_b:>13}  {'chars saved':>12}  agreement")
    agree = flips = 0
    stricter = looser = 0
    saved_total = 0
    for s in sessions:
        p_old, p_new = build_prompt(s, caps_a), build_prompt(s, NEW_CAPS)
        saved = len(p_old) - len(p_new)
        saved_total += saved
        try:
            v_old, sc_old = judge(p_old)
            v_new, sc_new = judge(p_new)
        except Exception as e:
            print(f"{s.name[:26]:26} ERROR: {str(e)[:60]}")
            continue
        same = v_old == v_new
        agree += same
        if not same:
            flips += 1
            # Which way did the smaller payload move the decision?
            if v_new in ("FAIL", "BLOCKED") and v_old == "PASS":
                stricter += 1
            elif v_new == "PASS" and v_old in ("FAIL", "BLOCKED"):
                looser += 1
        print(f"{s.name[:26]:26} {v_old + '/' + str(sc_old):>12} {v_new + '/' + str(sc_new):>12}  "
              f"{saved:12,}  {'same' if same else 'DIFFERENT'}")

    n = agree + flips
    print("\n=== SUMMARY ===")
    if n:
        print(f"verdict agreement : {agree}/{n} ({100*agree/n:.0f}%)")
        if args.control:
            print(f"flips             : {flips}   <- NOISE FLOOR (identical input both runs)")
            print("\nCompare with the A/B run. If A/B disagreement is not clearly worse than")
            print("this floor, the caps are not what moved the verdicts.")
        else:
            print(f"flips             : {flips}  (smaller payload stricter: {stricter}, looser: {looser})")
            print("\nRun again with --control before attributing any of this to the caps:")
            print("judge verdicts are stochastic, so some disagreement is noise.")
    print(f"prompt chars saved: {saved_total:,} across {len(sessions)} sessions "
          f"(~{saved_total//4:,} tokens, x{common.env_int('OUTCOME_FUSION_GATE_VOTES', 3)} votes per gate call)")
    if flips and looser and not args.control:
        print("\nNOTE: a LOOSER verdict on less context is the failure mode that matters —")
        print("it means the truncated evidence hid a real problem. Raise the caps via")
        print("OUTCOME_FUSION_MAX_PROOF_CHARS / OUTCOME_FUSION_MAX_TOOLLOG_CHARS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
