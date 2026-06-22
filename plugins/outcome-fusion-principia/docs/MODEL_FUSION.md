# Model fusion: the principles this plugin uses

This plugin is a **model-fusion system**: one model proposes the work (Claude),
a different model judges it (DeepSeek). That is the simplest case of a broad,
well-studied family. This note records what the research actually says and how
each principle is (or will be) applied here. It is evidence-locked: claims are
tied to sources, and contested points are marked.

> Honesty note: there is no public evidence that any specific frontier model
> ("Fable 5" or otherwise) reached its level *via* model fusion. The techniques
> below are documented research methods for getting more out of multiple models
> at inference time. We apply the principles; we do not claim a vendor recipe.

## What the literature says

**Mixture-of-Agents (MoA).** Multiple LLMs independently answer, then an
*aggregator* model synthesizes their answers into one. The aggregator
**combines** rather than **selects** — and that synthesis is what beats picking
the single best answer. Multi-proposer beats single-proposer; reported +8.2%
absolute on AlpacaEval 2.0 over GPT-4o. Roles split into **proposers** (diverse
perspectives) and **aggregators** (synthesis).
(arXiv 2406.04692; ICLR 2025; together.ai/blog/together-moa)

**LLM ensemble / knowledge fusion surveys.** Three families: output ensemble &
routing; knowledge fusion (combine probability distributions, e.g. FuseLLM/
FuseChat); parameter merging (model souping / merging). Output-level ensembling
is the only one available to a plugin — we cannot merge weights of hosted models.
(arXiv 2502.18036; arXiv 2401.10491; arXiv 2408.07990)

**Diversity matters, model-mixing is contested.** "Rethinking Mixture-of-Agents"
finds that mixing *different* models is not always better — **self-MoA** (the same
model sampled multiple times) can match or beat mixed-model MoA. The gain comes
from **diversity of independent attempts**, not necessarily from many vendors.
(arXiv 2502.00674, OpenReview ioprnwVrDH)

**The selection bottleneck.** Multi-agent pipelines lose value when they *select*
a single agent's output; aggregation and consistency help.
(arXiv 2603.20324; arXiv 2510.13855)

## How this plugin applies them

| Principle (sourced) | Application here |
|---|---|
| Two roles: proposer + judge | Claude proposes; DeepSeek is the independent judge. The judge is a *different model*, so it cannot rubber-stamp the proposer. |
| Diversity of independent attempts drives the gain (self-MoA) | `OUTCOME_FUSION_GATE_VOTES>1` samples the judge multiple times. v0.5.0 makes those samples **perspective-diverse** — each vote gets a different lens (evidence, completeness, simplicity, correctness) instead of identical re-rolls, which is the diversity the research says actually helps. |
| Aggregate, don't select | `aggregate_reviews` combines votes: conservative majority verdict, **unioned** next-actions, averaged score — it does not just pick one judge's answer. |
| Layered refinement | The gate's FAIL → continue → re-judge loop is a temporal MoA layer: each round refines against the prior critique. |
| Honesty: mixing isn't free or always better | Voting/aggregation are **opt-in** (default 1 sample). Telemetry (`metrics.jsonl`, `/cost`) makes the added cost visible so fusion is used deliberately. |

## Deliberately not done (and why)

- **Full MoA aggregator pass** (a synthesis LLM call that rewrites N critiques
  into one) — costs an extra call per gate; tracked as a future opt-in, not
  shipped on by default.
- **Knowledge fusion / weight merging** — impossible against hosted API models;
  we only have output-level ensembling.
- **A second vendor judge** — the architecture already supports it
  (`OUTCOME_FUSION_MODEL`), but the research says perspective diversity matters
  more than vendor diversity, so we add lenses first.

## Sources

- Mixture-of-Agents Enhances LLM Capabilities — https://arxiv.org/pdf/2406.04692
- Together MoA — https://www.together.ai/blog/together-moa
- Rethinking Mixture-of-Agents — https://arxiv.org/pdf/2502.00674
- LLM Ensemble survey — https://arxiv.org/pdf/2502.18036
- Knowledge Fusion of LLMs (FuseLLM) — https://arxiv.org/pdf/2401.10491
- FuseChat — https://arxiv.org/pdf/2408.07990
- Test-Time LLM Ensemble (consistency) — https://arxiv.org/pdf/2510.13855
