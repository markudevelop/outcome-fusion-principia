---
name: quant-aggregation-integrity
description: Verify and improve trading, options, portfolio, convex-tail, execution, and backtest claims using explicit mathematics, atomic observations, and empirical NBBO/fill data while preventing selection bias, leakage, overfitting, Jensen errors, cohort mixing, nonlinear risk understatement, commission errors, execution-stress double counting, arbitrary capital constraints, and opinion-based conclusions. Use for expected P&L, credits, fills, slippage, early exits, option payoffs, max loss, tail hedges, risk-return ratios, combined strategies, overlapping signals, maximum-dollar objectives, capital allocation, missing quote data, source-course strategy batches, and claims derived from averaged inputs or assumed execution. Require fail-closed rule/lifecycle/data/replay gates, governed finalization, and explicit handoff to the next catalog candidate only after the current candidate is genuinely ready.
---

# Quant Aggregation Integrity

Audit from the lowest available unit—trade, leg, timestamp, path, or account
event—and aggregate only after every nonlinear transformation and cost is
applied.

## Claim identity gate (mandatory before any test or verdict)

Treat the user's named strategy, source, course, rule version, or portfolio as
the estimand. Create a `claim_strategy_id` and a separate `tested_strategy_id`
before running code. Reconcile at minimum the source/rule identity, underlying,
structure and leg ratios, strike/body rule, tenor/expiry, entry timing,
eligibility and skip rules, adjustments, exit/settlement, execution unit,
fills, fees, sizing, and date scope.

- Never substitute an unrelated, convenient, or merely similarly named
  strategy for the user's named strategy. A different structure, lecture
  variant, source, or operational rule is a different estimand even when the
  payoff family sounds similar.
- Mark every field `exact`, `different`, or `unknown`. If any material field is
  `different` or `unknown`, the exact claimant status is `not_tested`.
- Do not issue a positive or negative edge verdict for the claimant from a
  proxy, neighboring candidate, generic engine default, or failed translation.
  A proxy may be tested only when the user explicitly authorizes a proxy or
  explicitly asks for a staged exploratory translation; label it `proxy` in
  every artifact, keep its result separate, and never use it to accept,
  reject, or rank the claimant.
- When the exact rule is incomplete, acquire the missing source/rules or ask
  for the missing decision boundary. Do not silently invent strike geometry,
  timing, adjustments, exits, package caps, or sizing to make the claim
  executable.
- Put these four lines in every report: `reproduced`, `corrected`,
  `unsupported`, and `not_tested`. The `not_tested` line must name the exact
  claimant whenever the tested object is a proxy.

## Source-course batch gate

For transcript/video/course corpora or a strategy database, read
the source-course batch gate section below
before analyzing or backtesting. Treat each strategy as a gated state machine:

`SOURCE_INVENTORIED` -> `RULE_MATRIX_FROZEN` -> `DATA_READY` ->
`IMPLEMENTED` -> `REPLAYED` -> `AUDITED` -> `ATLAS_FINALIZED` ->
`HANDOFF_READY`.

- Build the complete claimant-versus-tested rule matrix before writing outcome
  code. Include structure, cadence, eligibility, strike/tenor, management,
  delta scope, adjustment action, target/stop/breach, hedge quantity, order
  unit, fills, fees, sizing, NLV, and data coverage.
- Write the lifecycle state machine before simulating. Never infer “no
  adjustments” from silence; use it only when the source explicitly says so.
- If a material field is `different` or `unknown`, keep the exact claimant
  `not_tested`; label any neighboring replay as a separate proxy.
- Do not advance because a script ran. Require the atomic ledger, pre-spec,
  decision contract, rule-coverage audit, four-line report, governed wrapper,
  full finalizer check, and current Atlas projection.
- After a candidate reaches `HANDOFF_READY`, read the Dominion catalog and
  existing Atlas records, select the next untested strategy by source
  completeness/data feasibility/value of information, and write its pre-spec.
  Preserve blocked candidates and blockers; never silently convert a blocker
  into completion or skip a candidate without recording the handoff.

## Mandatory workflow

1. Define the estimand and unit explicitly: per ticket, active day, calendar
   day, contract, dollar at risk, or portfolio. Report multiple units
   separately when useful.
2. Build one atomic ledger with cohort/date, exact inputs, payoff, costs,
   risk, and inclusion flags. Preserve losing, missing, and rejected rows with
   status codes.
3. Filter the ledger to the claimed date scope before calculating any
   statistic. Never combine a mean from one period with counts or weights from
   another.
4. Calculate each trade's payoff, close value, max loss, return, and costs
   row by row. Aggregate those outputs; do not evaluate nonlinear formulas on
   averaged inputs.
5. Reconcile totals: `sum(ticket P&L) == sum(day P&L)`, ticket count equals
   the sum of daily tickets, and both-fire days contain two tickets when both
   are traded.
6. Reproduce the exact claimant first, then run the smallest direct
   falsification of that same claimant. If exact reproduction is impossible,
   stop the claimant verdict at `not_tested`; do not let a shortcut proxy
   disagreeing with the atomic replay become evidence against the claimant.
7. Save the ledger, executable audit, assumptions, and a machine-readable
   summary. Label descriptive, stressed, and executable results separately.

## Mathematical, empirical, and constructive standard

- Replace personal preference with a declared objective function, constraints,
  and observable estimand. Show the formula, inputs, units, and optimization
  domain before naming anything "best."
- Require both mathematical coherence and empirical testing. A payoff diagram
  without realized paths is a hypothesis; a historical average without a
  coherent payoff and risk model is not a strategy.
- Rank every feasible candidate on the same atomic cohort and execution model.
  Report the full frontier whenever different objectives produce different
  winners; never choose one using the assistant's taste.
- Distinguish in-sample discovery, held-out validation, live-paper evidence,
  and actual fills. Promote a tradable claim only at the strongest evidence
  level actually observed.
- Use constructive, action-positive language. Avoid opinionated dismissals
  such as "bad," "dead," or "cannot work." State the measured boundary,
  preserve the evidence, and immediately identify the nearest testable route
  to improvement.
- After every unsupported or losing candidate, generate and rank concrete
  positive follow-ups such as a changed structure, timing, hedge, execution
  rule, signal interaction, or data acquisition. Rank them by expected value
  of information, economic plausibility, and cost to test.
- End every study with: (1) the best currently supported action, (2) the best
  mathematically identified but unvalidated candidate, and (3) the next
  empirical experiment that can upgrade or reject it.
- Never manufacture positivity. Report losses, tail risk, and unsupported
  claims exactly; positivity means continuing the search intelligently, not
  hiding counterevidence or asserting an edge that data did not establish.

## Research validity and selection control

- Keep an immutable experiment ledger containing every attempted signal,
  parameter set, structure, universe, and result, including failures. Count
  all researcher degrees of freedom when assessing evidence.
- Freeze the rule, universe, timestamps, exclusions, sizing, costs, and primary
  statistic before opening held-out or forward data. Never tune on the final
  evaluation window and continue calling it out-of-sample.
- Use point-in-time features and causal availability timestamps. Audit time
  zones, daylight-saving transitions, revised data, survivorship, symbol
  changes, stale quotes, and corporate actions. Use purging and embargo where
  labels, positions, or information windows overlap.
- Adjust inference for the actual search. Use suitable controls such as
  family-wise error or FDR, White Reality Check/SPA, deflated Sharpe, PBO, and
  dependence-aware bootstrap. Report nominal statistics only as descriptive
  when the search history is incomplete.
- Demand robustness across adjacent parameters, subperiods, regimes, and
  plausible execution assumptions. Prefer a stable performance plateau over
  an isolated optimum. Report ex-best-trade/day results and concentration of
  P&L by date, regime, and market state.
- State an economic mechanism and its falsifiable predictions: who transfers
  the return, why they do so, when the premium should strengthen, and when it
  should weaken. Test those predictions separately from the optimized rule.
- Seek independent replication using a second data source, alternate
  implementation, or blind re-run before promotion when practical.

## Deployment and continuous-learning loop

- Size from the full empirical distribution and parameter uncertainty. Report
  risk of ruin, expected shortfall, ordered-path drawdown, margin usage,
  liquidity, and fractional-Kelly/log-growth frontiers without turning one
  utility function into the user's objective.
- Model portfolio contribution jointly. Measure correlation and shared tail
  states, overlapping signals, marginal expected shortfall, capital reuse,
  and whether diversification survives stressed regimes.
- Predefine promotion, scaling, pause, and retirement criteria. Move through
  historical discovery, frozen forward observer, paper/shadow execution,
  minimum live size, and staged scaling; never jump directly from optimized
  history to full capital.
- Compare live predictions with realized signals, fills, costs, risk, and P&L.
  Monitor feature drift, fill drift, calibration error, structural breaks,
  data outages, and limit breaches. De-risk through predefined rules rather
  than retrospective narratives.
- Attribute every live outcome to signal, sizing, market move, volatility,
  execution, fees, and hedge contribution. Feed deviations into new frozen
  experiments rather than silently rewriting the active rule.
- Prioritize the research queue by expected value of information multiplied by
  plausible economic value and divided by acquisition/testing cost. Favor
  targeted mechanism tests and neighboring structures over unconstrained
  parameter sweeps.

## Objective and capital-frontier integrity

- Treat the user's objective as an estimand, not a risk-preference debate.
  Never replace a maximum-dollar, capacity, or opportunity-set question with
  the assistant's preferred risk cap, risk tolerance, or utility function.
- When maximum dollars are requested, report both the equal-risk comparison
  and the capital frontier. Sweep the source/live cap, lower and higher caps,
  and an uncapped scaling case when the payoff model permits it.
- Never present one arbitrary cap as the total opportunity. If normalized P&L
  scales linearly with contracts, state that no finite backtest maximum exists
  without an account, margin, liquidity, or integer-contract constraint.
- Report factual frontier outputs at every checked capital point: total and
  marginal P&L, peak and average deployed risk, P&L per risk-dollar-day,
  Sharpe, ordered-path drawdown, worst day, ex-best-trade/day results, period
  splits, and execution scenarios.
- Treat overlapping independent signals as intentional confluence sizing
  unless the strategy explicitly makes them mutually exclusive. Combine them
  into one ticket quantity and one risk contribution; do not discard the
  second signal as a duplicate. Separately detect accidental duplicate orders.
- Distinguish `same-risk winner`, `maximum-dollar winner`, and `most
  capital-efficient winner`. They are different factual claims. Do not choose
  among them using the assistant's personal risk preference.
- If a cap is inherited from a live configuration, reproduce it exactly and
  identify it as a configured constraint. Also show the measurable opportunity
  above it rather than implying the configured cap proves capacity ends there.

## Empirical data acquisition is mandatory

- Treat a missing local quote, fill, chain, or path as an acquisition task,
  not permission to assume an answer or stop the research. Inventory all
  workspace caches, broker exports, order/fill logs, related repositories,
  and configured historical-data providers before declaring a field absent.
- When the required slice is not cached, build or run the smallest reproducible
  extraction/backfill job needed to obtain it. Record source, contract
  identity, timestamp/time zone, retrieval status, and coverage in the atomic
  ledger. Retry or source an independent dataset when practical.
- Never substitute an assumed midpoint, spread, slippage, fill probability,
  or liquidity haircut for empirical NBBO/fill data that can be obtained.
  Keep unresolved observations status-coded until acquired. Assumptions may
  appear only as separately labeled stress scenarios, never as primary proof.
- Reconstruct execution at the order's true unit. Prefer actual combo-order
  fills and contemporaneous package NBBO when available. If only leg NBBO is
  available, aggregate the exact simultaneous legs and label it a leg-NBBO
  estimator rather than package-NBBO evidence.
- Calibrate fillability empirically from actual orders: compare limit price,
  contemporaneous NBBO/package market, fill price, latency, size, time of day,
  and fill/no-fill outcome. Report coverage and the distribution of price
  improvement or shortfall; do not declare midpoint true or false by intuition.
- A real data-access failure can limit a specific result, but it must end with
  an executable acquisition plan or collector, not the generic conclusion
  that the test cannot be performed.

before accepting, correcting, or rejecting the capital rule.

## NLV, compounding, and sizing-policy guardrails

- Declare the sizing-state policy before replaying: `fixed_notional`,
  `frozen_start_of_day_nlv`, or `intraday_mark_to_market_nlv`. Treat them as
  different strategies, not alternative labels for one result.
- Never call `initial_nlv * cumprod(1 + fixed_pnl / initial_nlv)` a replay of
  an NLV-sized strategy. It is only a mathematical transformation of a
  fixed-notional P&L stream.
- When NLV affects credit budgets, strikes, quantities, integer rounding,
  margin admission, or later allocations, simulate sequentially. For each
  sizing event, rebuild the atomic ticket from the causally available NLV,
  realize its path and costs, update equity at the rule's specified time, and
  only then size later tickets or sessions.
- For a daily-frozen policy, use prior-close equity plus explicitly modeled
  cash flows, capture one restart-safe NLV snapshot before the first entry,
  and hold it constant for every sleeve and slot that trade date. Do not let
  same-day gains or losses resize later entries.
- For an intraday-NLV policy, reconstruct contemporaneous broker NLV from
  actual account marks when available. If only option quote mids or synthetic
  marks exist, label the result a modeled proxy and never claim exact
  production parity.
- Reproduce the fixed-notional baseline through the new sequential engine and
  require zero or declared-tolerance day-level differences before accepting a
  compounded comparison. This control must fail closed.
- Report starting NLV, ending NLV, cash flows, daily return denominator,
  CAGR, ordered-path drawdown, worst-day return, defined risk/NLV, margin/NLV,
  integer quantities, and capacity separately. State whether drawdown uses
  daily closes or intraday equity.
- Keep `same-notional strategy comparison`, `causal account compounding`, and
  `executable broker-capacity path` as separate estimands. A high compounded
  ending balance is not executable evidence when quantity, displayed depth,
  buying power, or order-rate limits were not applied.
- Before saying live and backtest use the same sizing logic, inspect and
  reconcile the exact NLV source, snapshot timestamp, refresh frequency,
  restart behavior, deposits/withdrawals, open-position marks, and fallback
  behavior in both code paths.
- Treat prior-close strategy equity and first-entry full-account broker NLV as
  different estimands. The former can support a causal capacity scenario; the
  latter is the live account-risk denominator. Never call either an exact
  replay of the other without timestamped broker marks, account cash flows,
  unrelated-position marks, and the same margin-admission path.

## Stop, hard-loss, and drawdown guardrails

- Treat `stop trigger multiple`, `stop fill multiple`, `atomic defined hard
  loss`, `exact portfolio terminal hard loss`, and `historical drawdown` as
  different quantities. Never use one as a synonym or proxy for another.
- Translate option-premium stops explicitly. A short bought back at `k` times
  entry premium has a pre-cost short-leg loss of about `(k - 1)` entry
  premiums; it is not a `k`-times loss of the spread risk or account.
- Rebuild stops at the true unit and path. Count triggers, fills, trigger-to-fill
  overshoot, unfilled stop-limits, per-side stops, both-side sequential stops,
  and the maximum stopped sides per day. Derive the count from actual submitted
  tickets, sleeves, and slots: six time slots with two condor sleeves can
  produce up to twelve condors and twenty-four sequential short-side stops,
  even though put and call terminal tail losses cannot occur at one settlement
  price.
- Compute atomic defined loss from exact widths, quantities, net credits,
  commissions, and entry costs. For an unequal put/call condor use the maximum
  feasible terminal side loss, not the sum of mutually exclusive tails.
- Compute exact portfolio terminal hard loss by aggregating every open leg and
  evaluating the combined payoff at every strike breakpoint and both tails.
  Sum of ticket-level maxima may be retained as a conservative reservation,
  but label it separately from the tighter portfolio payoff bound.
- When stops can realize losses and later entries can add exposure, terminal
  payoff is not the complete day bound. Rebuild the ticket set causally under
  each stop rule because stop times can free strikes, margin, or capacity. Then
  add realized/capped stop losses to the remaining portfolio payoff at one
  terminal underlying value. If independently selecting each side's adverse
  stop state is used as an upper bound, label it a conservative selected-book
  scenario and disclose that joint path attainability is not proven.
- A stop-limit cap bounds the authorized fill price, not the realized loss and
  not fillability. If the market gaps through the cap, preserve the unfilled
  path and let the actual long-wing payoff define the hard settlement bound.
  Reconcile entry stops, restart/watchdog replacements, and manual fallbacks;
  every path must use the researched spread-specific cap or be labeled a
  different strategy.
- Report realized worst day and expected shortfall beside theoretical hard
  loss. A historical drawdown ceiling is a sample-path observation, never a
  guarantee that defined risk, intraday loss, gap loss, or future drawdown is
  below that percentage.

## Production-parity guardrails for multi-sleeve books

- Never call an independently aggregated sleeve ledger production-executable
  until the exact live order generator reproduces it. Independent sleeves may
  select contracts that cannot coexist once broker and account state are
  shared.
- Replay the selector chronologically at the atomic order/ticket level. Include
  same-contract and same-strike rules, open short positions, working stop/TP
  children, persistent long wings, stopped-short release times, same-signal
  cross-sleeve exclusions, strike-reuse/merge limits, and broker prohibitions
  on opposing opening/closing orders.
- Reproduce every live budget and sizing ledger: which sleeves consume credit
  intent, whether side shares use planned or filled credit, per-slot caps,
  delta/premium affordability filters, integer residual carry, retries,
  restart persistence, and any post-selector BP multiplier. Do not replace
  these with the research runner's cleaner independent budgets.
- Keep `independent-sleeve research book`, `joint executable selector book`,
  and `actual broker-filled book` as separate estimands. Report the P&L,
  Sharpe, drawdown, tail, and validation delta lost at each transition.
- Require a fail-closed production-parity gate before deployment: fingerprint
  the exact config and source, reconcile deterministic selector fixtures,
  model live constraints across the full historical ledger, and retain the
  prior strategy when the candidate cannot reproduce or beat its governed
  executable comparator.
- A safety patch must itself be represented in the replay. Examples include
  blocking a later sleeve from shorting an earlier sleeve's same-signal wing,
  enforcing researched wing-width caps, and releasing a stopped short before
  later slots only when the modeled or actual stop fill time supports it.
- Before declaring a live service healthy or down, discover the installed
  service-unit name, container name, selected-strategy pointer, and health
  endpoint from the host itself. Verify that exact unit and container, exact
  immutable image digest and source SHA, restart count, broker/data mode, and
  rollback target. An assumed service name is neither outage evidence nor a
  health check.
- Verify that every production scheduler wakes before the earliest required
  feature-capture window, including a cold start after weekends/holidays and a
  same-day restart. Waking before the first order is insufficient when a
  frozen signal snapshot is earlier. Persist the first valid snapshot,
  classify once, make later ticks/restarts immutable, and expose the missing-
  snapshot fallback or fail-closed reason in telemetry.

## Nonlinear guardrails

- Treat `E[f(X)]` and `f(E[X])` as different unless linearity is proved.
- For asymmetric defined-risk iron flies, compute per ticket:
  `max(ATM-put_wing, call_wing-ATM) * multiplier - entry_credit`.
  Never use the smaller wing, an average wing, or a payoff built from mean
  strikes.
- Compute intrinsic or mark-to-market P&L for every realized terminal/exit
  state. Never plug mean spot, mean strike, mean credit, or mean width into an
  option payoff.
- Label both `mean(P&L/risk)` and `sum(P&L)/sum(risk)` if either is relevant.
  They answer different questions. Never call `mean(P&L)/mean(risk)` the
  average trade return without proving the weights match.
- Calculate compounding from the ordered equity path. Do not compound the
  arithmetic mean return.
- Calculate drawdown from the ordered equity path, not from average losses.

## Convexity and asymmetric-payoff guardrails

- Identify the sign and source of convexity before judging a strategy. Never
  apply a short-premium acceptance rule to a long-convex bet, or reward a
  short-convex strategy merely for a high win rate.
- For long convexity, treat the premium and repeated carry burn as the known,
  budgeted loss. A low win rate, negative standalone carry, or poor standalone
  Sharpe does not by itself invalidate the trade. Paying $10 can be rational
  when it buys a credible, executable payoff orders of magnitude larger in a
  valuable state.
- Verify the convex payoff atomically across price and volatility paths. Check
  premium, maximum loss, roll schedule, expiry mismatch, path dependence,
  gamma, vega, skew, liquidity, gap behavior, and whether the quoted tail
  payoff can actually be monetized.
- Report tail multiples and state-conditional outcomes: payoff/premium,
  crisis-period P&L, expected shortfall contribution, worst-base-book-day
  contribution, drawdown offset, and payoff timing. Do not summarize a convex
  distribution with win rate or mean P&L alone.
- Judge a convex sleeve primarily by its marginal effect on the full ordered
  portfolio path. Compare base versus base-plus-sleeve CAGR or geometric
  growth, maximum drawdown, expected shortfall, recovery time, ruin risk, and
  capital efficiency at several fixed premium budgets.
- Keep three claims separate: negative carry, positive standalone expectancy,
  and positive portfolio insurance value. A sleeve may fail the second and
  still pass the third because its payoff arrives when marginal capital is most
  valuable.
- For short convexity, invert the burden of proof: frequent small gains are not
  enough. Stress clustered gaps, volatility expansion, liquidity withdrawal,
  correlation jumps, and the largest feasible loss before calling it an edge.

## Execution and portfolio guardrails

- Credit is cash received, not expected profit. Subtract the realized payoff
  or exact close debit and all commissions before reporting P&L.
- A settlement backtest does not validate an early buyback. Reprice the exact
  four legs at the claimed exit timestamp using documented bid/ask rules.
- Keep execution scenarios distinct:
  entry/exit midpoint, marketable cross, and any additional haircut. Do not
  silently use a haircut as a substitute for an early exit or apply both
  while describing only one.
- Use observed NBBO and broker fills to define the primary execution model.
  Midpoint and full-cross remain useful boundaries, but neither replaces an
  empirical fill distribution when order-level evidence exists or can be
  extracted.
- State whether commission is per side, per contract, or round trip. An early
  close normally creates another four option-contract transactions; a
  settlement exit does not.
- Distinguish tickets, unique active days, and underlying-level signals.
  If both underlyings fire and both are taken, one date contributes two
  tickets but one active day.
- For multi-underlying portfolios, use the union of eligible observations
  unless the claim explicitly requires a common-calendar comparison. Explain
  any dates discarded by an intersection.

## Decision standard

Use the labels `reproduced`, `corrected`, `unsupported`, and `not tested`.
Separate evidence that an effect exists in the checked history from evidence
that its exact execution rule, capacity, and prospective edge are validated.
Do not convert data limitations or selection concerns into a claim that a
measured historical result is unreal.
