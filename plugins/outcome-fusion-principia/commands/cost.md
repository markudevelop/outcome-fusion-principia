Show the DeepSeek usage and cost for the active Outcome Fusion session.

Read `.ai/outcome_fusion/current_session.txt`, then read
`.ai/outcome_fusion/sessions/<session>/metrics.jsonl`.

Each line is one DeepSeek call: `label`, `input_tokens`, `output_tokens`,
`latency_ms`. Total them and report only:

1. Total calls
2. Total input / output / combined tokens
3. Average latency per call (ms)
4. Breakdown of calls by label (e.g. `mission_compile`, `release_gate`)

If `metrics.jsonl` does not exist yet, say there is no usage recorded for this
session.
