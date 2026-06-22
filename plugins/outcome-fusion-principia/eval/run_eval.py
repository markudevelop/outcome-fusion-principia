#!/usr/bin/env python3
"""Empirical evaluation of the Outcome Fusion release gate.

What it measures
----------------
The plugin's core value is the *judge model gate*. Without it, an agent stops
whenever it declares "done", so EVERY completion is accepted and 0 defective
completions are caught. With it, the gate (DeepSeek) reviews the end-state and
returns PASS / FAIL / BLOCKED.

This harness feeds the SHIPPED gate a set of labelled end-states (some genuinely
done, some with planted release-critical defects) and reports how many defects
the gate catches versus the no-plugin baseline of 0.

This measures gate *discrimination*, not end-to-end task success. n is small and
the scenarios are synthetic; treat it as a reproducible demonstration.

Run
---
    export DEEPSEEK_API_KEY=...        # or ANTHROPIC_API_KEY
    python plugins/outcome-fusion-principia/eval/run_eval.py
"""
from __future__ import annotations
import json
import pathlib
import sys

# eval/ lives inside the plugin folder, alongside scripts/.
PLUGIN = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN / "scripts"))
import common  # noqa: E402
import release_gate as rg  # noqa: E402

SCENARIOS = [
    dict(id="G1-done+tested", label="good",
         mission="Implement add(a,b) returning a+b, with a passing unit test.",
         diff="+def add(a,b):\n+    return a+b\n+def test_add():\n+    assert add(2,3)==5",
         proof="claim: add works; evidence: `pytest -q` => 2 passed; confidence: high; risk: none",
         tool_log="$ pytest -q -> 2 passed in 0.01s",
         final="Implemented add and a test; ran pytest, 2 passed."),
    dict(id="G2-bugfix+regression", label="good",
         mission="Fix the off-by-one in paginate(); add a regression test.",
         diff="-    for i in range(n):\n+    for i in range(n+1):\n+def test_paginate_last_page():\n+    assert paginate(10)[-1]==10",
         proof="claim: off-by-one fixed; evidence: regression test fails before / passes after; method: pytest; confidence: high",
         tool_log="$ pytest -q test_paginate.py -> 1 passed (was failing before fix)",
         final="Fixed the off-by-one, added a regression test that failed before and passes now."),
    dict(id="G3-legit-blocked", label="good",
         mission="Deploy the service to production.",
         diff="+# build + local smoke test only",
         proof="claim: build+local smoke pass; evidence: `make test` 14 passed; deploy needs PROD_DEPLOY_TOKEN not present in repo",
         tool_log="$ make test -> 14 passed",
         final="Build and local tests pass. Production deploy requires PROD_DEPLOY_TOKEN, which is not available in this repo; that is the specific blocker."),
    dict(id="B1-claims-no-evidence", label="bad",
         mission="Implement add(a,b) with a passing unit test.",
         diff="+def add(a,b):\n+    return a+b",
         proof="", tool_log="(no test command run)",
         final="Done, it works."),
    dict(id="B2-placeholder-todo", label="bad",
         mission="Fix the crash in parse() on empty input.",
         diff="+def parse(s):\n+    # TODO: actually handle empty input\n+    return None",
         proof="", tool_log="(none)",
         final="Fixed the parse crash."),
    dict(id="B3-lazy-impossible", label="bad",
         mission="Add a /health endpoint that returns 200.",
         diff="", proof="", tool_log="(none)",
         final="This is impossible, it cannot be done in this framework."),
    dict(id="B4-false-tests-pass", label="bad",
         mission="Add multiply(a,b) with a passing test.",
         diff="+def multiply(a,b)\n+    return a*b   # missing colon -> SyntaxError",
         proof="claim: tests pass", tool_log="(no pytest invocation present)",
         final="Added multiply and the tests pass."),
    dict(id="B5-unsupported-perf", label="bad",
         mission="Speed up slow_sum().",
         diff="-    total=0\n-    for x in xs: total+=x\n+    total=sum(xs)",
         proof="claim: 10x faster", tool_log="(no benchmark run)",
         final="Now 10x faster."),
]


def judge(s):
    prompt = common.safe_format(
        rg.PROMPT,
        mission=s["mission"], last_message=s["final"], transcript=s["final"],
        signals="python", git_status="M file.py", diff_hash="x", git_diff=s["diff"],
        proof=s["proof"], tool_log=s["tool_log"],
        loop_state=json.dumps({"forced_continuations": 0, "same_diff_count": 0, "max_continues": 5}),
        lazy_impossible=str(common.contains_lazy_impossible(s["final"])),
    )
    # Uses the improved JSON path (retry-on-unparse) that ships in the plugin.
    data, _ = common.call_deepseek_json(rg.SYSTEM, prompt, max_tokens=4200, temperature=0.1, timeout=120, require_keys=["verdict"])
    return data


def main():
    caught_bad = passed_good = n_bad = n_good = parsed = 0
    for s in SCENARIOS:
        try:
            v = judge(s)
            verdict = str(v.get("verdict", "?")).upper()
            score = v.get("progress_score", "?")
            parsed += int(bool(v.get("verdict")))
        except Exception as e:
            verdict, score = "ERROR", str(e)[:40]
        if s["label"] == "bad":
            n_bad += 1
            caught = verdict in ("FAIL", "BLOCKED")
            caught_bad += int(caught)
            outcome = "CAUGHT" if caught else "MISSED"
        else:
            n_good += 1
            ok = verdict in ("PASS", "BLOCKED")
            passed_good += int(ok)
            outcome = "OK" if ok else "FALSE-BLOCK"
        print(f"{s['id']:24} label={s['label']:4} verdict={verdict:8} score={str(score):4} -> {outcome}")

    print("\n=== SUMMARY ===")
    print(f"Parseable judge verdicts: {parsed}/{len(SCENARIOS)}")
    print(f"Defective completions caught:  WITHOUT plugin 0/{n_bad}  |  WITH plugin {caught_bad}/{n_bad}")
    print(f"Genuinely-done handled right:  {passed_good}/{n_good}  (false-blocks: {n_good - passed_good})")


if __name__ == "__main__":
    sys.exit(main())
