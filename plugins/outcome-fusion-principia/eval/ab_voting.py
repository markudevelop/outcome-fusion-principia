#!/usr/bin/env python3
"""A/B: does perspective-diverse voting (GATE_VOTES>1) beat a single judge sample?

Runs the same labelled scenarios through the exact shipped gate logic at
votes=1 and votes=3, and compares defect catch rate and false-block rate. The
hypothesis (from the Mixture-of-Agents literature, docs/MODEL_FUSION.md) is that
diversity reduces the stochastic false-blocks on genuinely-done work without
losing defect catch.

    export DEEPSEEK_API_KEY=...
    python plugins/outcome-fusion-principia/eval/ab_voting.py          # 1 trial
    OF_AB_TRIALS=2 python plugins/outcome-fusion-principia/eval/ab_voting.py
"""
from __future__ import annotations
import json
import os
import pathlib
import sys

PLUGIN = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN / "scripts"))
sys.path.insert(0, str(PLUGIN / "eval"))
import common  # noqa: E402
import release_gate as rg  # noqa: E402
from run_eval import SCENARIOS  # noqa: E402


def _rendered(s):
    return common.safe_format(
        rg.PROMPT,
        mission=s["mission"], last_message=s["final"], transcript=s["final"],
        signals=s.get("signals", "python"), git_status=s.get("git_status", "M file.py"),
        diff_hash="x", git_diff=s["diff"], proof=s["proof"], tool_log=s["tool_log"],
        loop_state=json.dumps({"forced_continuations": 0, "same_diff_count": 0, "max_continues": 5}),
        lazy_impossible=str(common.contains_lazy_impossible(s["final"])),
    )


def gate_verdict(s, votes):
    """Replicates release_gate's voting path exactly."""
    rendered = _rendered(s)
    lenses = common.vote_lenses(votes)
    temp = 0.1 if votes == 1 else 0.4
    reviews = []
    for i in range(votes):
        prompt_i = rendered if not lenses[i] else rendered + "\n\n" + lenses[i]
        one, _ = common.call_deepseek_json(rg.SYSTEM, prompt_i, max_tokens=4200, temperature=temp, timeout=120, require_keys=["verdict"])
        if one:
            reviews.append(one)
    agg = common.aggregate_reviews(reviews)
    return str(agg.get("verdict", "?")).upper()


def run_setting(votes, trials, scenarios):
    caught = good_ok = n_bad = n_good = 0
    for t in range(trials):
        for s in scenarios:
            v = gate_verdict(s, votes)
            if s["label"] == "bad":
                n_bad += 1
                ok = v in ("FAIL", "BLOCKED")
                caught += int(ok)
                mark = "CAUGHT" if ok else "MISSED"
            else:
                n_good += 1
                ok = v in ("PASS", "BLOCKED")
                good_ok += int(ok)
                mark = "OK" if ok else "FALSE-BLOCK"
            print(f"  votes={votes} t{t} {s['id']:24} -> {v:8} {mark}", flush=True)
    return caught, n_bad, good_ok, n_good


def main():
    trials = max(1, int(os.getenv("OF_AB_TRIALS", "1")))
    good_only = os.getenv("OF_AB_GOOD_ONLY", "").strip().lower() in {"1", "true", "yes"}
    scenarios = [s for s in SCENARIOS if s["label"] == "good"] if good_only else SCENARIOS
    print(f"A/B over {len(scenarios)} scenarios x {trials} trial(s) "
          f"({'good-only' if good_only else 'all'})\n", flush=True)
    for votes in (1, 3):
        caught, nb, good_ok, ng = run_setting(votes, trials, scenarios)
        fb = ng - good_ok
        catch = f"{caught}/{nb}" if nb else "n/a"
        print(f"==> votes={votes}: defects caught {catch} | "
              f"good handled {good_ok}/{ng} | false-blocks {fb}/{ng}\n", flush=True)
    print("Hypothesis: votes=3 keeps catch high and lowers false-blocks. Small n — directional.", flush=True)


if __name__ == "__main__":
    sys.exit(main())
