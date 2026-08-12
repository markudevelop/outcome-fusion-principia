#!/usr/bin/env python3
"""Break the plugin on purpose and check the test suite notices.

A green suite proves nothing on its own. Most of this repo's original tests
assert that doctrine TEXT appears in a prompt, which catches a deleted rule but
would not catch a gate that blocks every turn, allows every turn, or writes the
model's scratchpad into the mission. This script answers the only question that
matters about a test suite: **if the code were broken, would anything fail?**

Each mutant is a one-line edit that reintroduces a real defect — several of them
bugs this plugin actually shipped. A SURVIVED mutant is a hole in the suite.

    python plugins/outcome-fusion-principia/eval/mutation_check.py
    python plugins/outcome-fusion-principia/eval/mutation_check.py --list

Exit code is non-zero if any mutant survives, so CI can enforce it.
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

PLUGIN = pathlib.Path(__file__).resolve().parent.parent
REPO = PLUGIN.parent.parent

# (name, file, find, replace) — each reintroduces a defect that must be caught.
MUTANTS: list[tuple[str, str, str, str]] = [
    ("gate ignores stop_hook_active (infinite self-loop)",
     "scripts/release_gate.py",
     'if payload.get("stop_hook_active"):\n        return 0',
     'if False:\n        return 0'),
    ("gate always PASSes",
     "scripts/release_gate.py",
     'verdict = str(review.get("verdict", "FAIL")).upper()',
     'verdict = "PASS"'),
    ("gate always FAILs",
     "scripts/release_gate.py",
     'verdict = str(review.get("verdict", "FAIL")).upper()',
     'verdict = "FAIL"'),
    ("gate bills question turns for a vote round",
     "scripts/release_gate.py",
     "if read_turn_mode(wdir) == INTENT_QUESTION:\n        return 0",
     "if False:\n        return 0"),
    ("gate never stops forcing continuation",
     "scripts/release_gate.py",
     'if int(state.get("continues", 0)) >= max_continues:',
     "if False:"),
    ("same-diff guard stops counting repeats",
     "scripts/release_gate.py",
     'state["same_diff_count"] = int(state.get("same_diff_count", 0)) + 1',
     'state["same_diff_count"] = 0'),
    ("compiler writes raw model output (the reasoning leak returns)",
     "scripts/compile_prompt.py",
     "mission = clean_mission(call_deepseek(",
     "mission = (call_deepseek("),
    ("compiler skips the usability check",
     "scripts/compile_prompt.py",
     "if not mission_is_usable(mission):",
     "if False and not mission_is_usable(mission):"),
    ("secret scan reports nothing",
     "scripts/common.py",
     'findings.append(f"{where}: {label}")',
     "pass"),
    ("secret scan stops distinguishing fixtures from app code",
     "scripts/common.py",
     "if _is_fixture_path(current):",
     "if True:"),
    ("vote aggregation removed",
     "scripts/common.py",
     "def aggregate_reviews(",
     "def aggregate_reviews_DISABLED("),
    ("tool log framing reverts to a raw character tail",
     "scripts/common.py",
     "    starts = [m.start() for m in _TOOL_LOG_ENTRY.finditer(text)]",
     "    return text[-budget:]\n    starts = [m.start() for m in _TOOL_LOG_ENTRY.finditer(text)]"),
    # Faithful to the shipped bug: it was the SINGLE QUOTES, not the shell as
    # such. A joined argv without quotes still works under cmd.exe, so a mutant
    # that merely drops run_argv SURVIVES and falsely reports a hole in the
    # suite. Measured both ways before fixing this entry.
    ("git runs back through the shell with a quoted pathspec (Windows blind-diff bug)",
     "scripts/common.py",
     "raw_diff = run_argv(GIT_DIFF_ARGV, cwd, timeout=30, limit=limit, redact_output=False)",
     "raw_diff = run_cmd(\"git diff -- . ':(exclude).git' ':(exclude)node_modules'\", cwd, timeout=30, limit=limit, redact_output=False)"),
    ("gate state collides between repos sharing a folder name",
     "scripts/common.py",
     'return plugin_data_dir(payload) / f"{clean}_{sha(str(cwd.resolve()))[:8]}_state.json"',
     'return plugin_data_dir(payload) / f"{clean}_state.json"'),
    ("redaction disabled (credentials reach the judge)",
     "scripts/common.py",
     "def redact(text: str, limit: int | None = None) -> str:",
     "def redact(text: str, limit: int | None = None) -> str:\n    return text if limit is None else text[-limit:]"),
]


def run_suite() -> tuple[bool, str]:
    """(suite_passed, tail_of_output).

    The test path is absolute on purpose. A relative "tests/" resolved against
    the repo root does not exist here, so pytest exited 4 (usage error) on every
    run — which reads as "mutant caught" for EVERY mutant, including ones nothing
    tests. That false 8/8 is exactly the failure this script exists to prevent,
    so the baseline check below refuses to run unless the command really works.
    """
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "--no-header",
         "-p", "no:cacheprovider", str(PLUGIN / "tests")],
        cwd=REPO, capture_output=True, text=True, timeout=900,
    )
    return r.returncode == 0, (r.stdout or r.stderr)[-400:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="list mutants without running them")
    args = ap.parse_args()

    if args.list:
        for name, path, _, _ in MUTANTS:
            print(f"  {path:28} {name}")
        return 0

    print("Baseline: the suite must pass before mutating.")
    ok, tail = run_suite()
    if not ok:
        print("  BASELINE FAILS — every mutant would look 'caught' for the wrong reason.")
        print("  " + tail.replace("\n", "\n  "))
        return 2
    # A usage or collection error also exits non-zero, so confirm tests RAN.
    if " passed" not in tail:
        print("  BASELINE RAN NO TESTS — the command is wrong, not the code.")
        print("  " + tail.replace("\n", "\n  "))
        return 2
    print(f"  baseline green — {tail.strip().splitlines()[-1].strip()}\n")

    print(f"Mutation testing {len(MUTANTS)} defects — does the suite notice?\n")
    survived, skipped = [], []
    for name, relpath, old, new in MUTANTS:
        target = PLUGIN / relpath
        original = target.read_text(encoding="utf-8")
        if old not in original:
            skipped.append(name)
            print(f"  {'SKIP':10} {name}  (pattern not found — mutant is stale)")
            continue
        try:
            target.write_text(original.replace(old, new, 1), encoding="utf-8")
            caught = not run_suite()[0]
        finally:
            target.write_text(original, encoding="utf-8")
        if not caught:
            survived.append(name)
        print(f"  {'CAUGHT' if caught else '*SURVIVED*':10} {name}")

    tested = len(MUTANTS) - len(skipped)
    print(f"\n  caught {tested - len(survived)}/{tested} live mutants"
          + (f", {len(skipped)} stale" if skipped else ""))
    if survived:
        print("\n  UNDETECTED — the suite has a hole for each of these:")
        for s in survived:
            print(f"    - {s}")
        return 1
    if skipped:
        print("\n  Stale mutants target code that has moved; update them or drop them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
