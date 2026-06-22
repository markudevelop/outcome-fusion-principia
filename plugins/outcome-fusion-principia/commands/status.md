Show Outcome Fusion status for the active Claude session.

Read `.ai/outcome_fusion/current_session.txt`, then read the matching session folder under `.ai/outcome_fusion/sessions/<session>/`:

1. `mission.md`
2. `proof.md`
3. `review.md`
4. `closure.md`
5. `tool_log.md`

Also read `.ai/outcome_fusion/memory.md` if present.

Return only:

1. Active session id
2. Mission status
3. Current blocker
4. Verified evidence
5. Unsupported claims
6. Simplify or remove
7. Next best test
