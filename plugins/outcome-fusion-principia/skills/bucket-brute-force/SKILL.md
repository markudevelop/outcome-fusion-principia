---
description: Default edge-discovery method for trading and quantitative research — do not tune one rule until it looks good; cut the full honest event set by many pre-declared, decision-time-knowable dimensions at once and keep only buckets that pay in BOTH halves of history. Use whenever asked to find, brute-force, or sweep signals, buckets, or ideas; to find "where it works"; to improve or rescue a strategy; to decide whether a filter is real; to reduce drawdown; or before accepting ANY backtest headline.
---

# Bucket brute-force (default discovery method)

The framing: **nothing is dead — you brute-force into buckets and find where it
works.** Rule-tuning cannot tell an edge from a leak, because it maximises either
one with equal enthusiasm. The bucket sweep asks a different question: *which
cells of the honest event set pay in both halves of history?*

## Why this is the default

A monthly re-fitting optimiser once shipped a gap-fade champion at **CAGR +1051%,
Sharpe 6.20**. It reproduced exactly and was still fiction: its volume filter used
the gap day's **full-session** volume, unknowable at the 09:30 entry. Lagged
properly it was **+47.9%, Sharpe 1.28**. No amount of tuning would have surfaced
that; a bucket sweep over decision-time-knowable dimensions found the honest
replacement the same night.

The method then audited its own output. Re-swept inside the surviving gate and
replicated on a second feed, the four "confirmations" stacked on top of the gate
were **worse than the bare gate** on both feeds (Sharpe 1.18/0.95 vs 1.80/1.94).
Selectivity buys expectancy and sells frequency — annualise over the calendar or
you will not see the bill.

## The seven steps

1. Build the **full honest event set** first — no filters, point-in-time
   universe, no survivorship shortcuts. **Filters are the output, not the input.**
2. Write a **lag manifest**: every dimension gets one line stating as-of when it
   is knowable at decision time. No as-of, no sweep.
3. **Bucket by concept** (meaningful cut edges); use quantiles only where there
   is no natural edge.
4. Split **TRAIN (older) / TEST (newer)**. A bucket survives only if **both**
   halves beat the baseline of the same event set. Count per-year signs too.
5. Publish the **hypothesis count H** and the noise bar `sqrt(2·ln H)`, applied
   to each bucket's **lift over the rest of the sample** with a **date-clustered
   standard error**. Not its t against zero — that is large for every cell when
   the baseline is positive. Not an unclustered SE — 20 events sharing one
   session's move are not 20 observations, and measured, that error made a
   weekday bucket fire on every permutation sweep. A lift-t below the bar is
   breadth, not an edge.
6. Combine into a score whose components and cutoffs are fixed on the **train
   half alone**; then check monotonicity of the outcome in the score on test.
7. Only then size it: cost, per-name cap, capacity. **Drawdown is a sizing
   artifact** — the per-name cap sets DD while Sharpe barely moves.

## Split every lift into timing and picking

`mean(bucket) − mean(all)` decomposes exactly into a BETWEEN-day term (which
sessions the bucket fires on) and a WITHIN-day term (which names it picks inside
them). Report both.

A feature that is constant within a session has within ≡ 0 and is therefore a
**market-timing claim needing a day-count sample, not an event-count one** —
which is usually far less data than the event count flatters you into thinking.
Measured on one gap panel, the real survivors were majority within (gap>20%:
+44 between / +236 within) while a dead-cat bucket was +19 between / −1 within:
no cross-sectional edge at all, it simply fired on days that faded.

## Validate the method on your panel before trusting a sweep

Permute the outcome to get the **empirical null**, and use that rather than the
`sqrt(2·ln H)` formula. Measured over 200 permutations on a 62,756-event panel,
the formula said 2.60 while the null's p95 was 2.74 globally and 3.44
within-date (which preserves the day-effect structure).

Plant known lifts to measure detection power. On that same panel the minimum
detectable lift at 80% power was 25 bps in a 31,335-event bucket but worse than
200 bps in a 602-event one — so **a null result below your measured MDL means no
power, not no effect.**

The same validation shows an outcome-derived feature clearing every statistical
gate. Only the lag manifest stops that leak; statistics never will.

Run this once per panel. It takes minutes.

## Non-negotiables

- **Cross-check a second data feed** before believing the map. One free feed
  overstated a gap-fade's open→close edge by +59 bps/trade against a paid SIP
  feed; the broad version flipped negative while the selective one got stronger.
- **Don't rebuild a leak with legal data.** It usually is not reconstructible —
  tested, a "predicted-quiet" subset earned *less* than no filter at all.
- **Every grid dimension needs a "no filter" option**, or the search is force-fed.
- **Report the dead ideas as explicitly as the live ones.** The negative half of
  a sweep is half its value.

## Runner interface

Any event-table sweeper works if it takes: the event table, the outcome column,
repeated feature/dimension arguments, and a lag manifest it refuses to run
without. Keep the manifest a required input, not an optional flag — that is the
single control that separates this method from a faster way to fool yourself.

Related: `quant-aggregation-integrity` (how not to fool yourself when measuring),
`quant-scientist` (fast triage of a market claim).
