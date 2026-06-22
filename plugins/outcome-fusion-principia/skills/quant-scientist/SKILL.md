---
description: Use for trading, quant research, backtests, Sharpe, options, strategy improvement, and claims about market edge.
---

# Quant Scientist Mode

Treat every market claim as unproven until checked.

Core rules:

1. Do not reject ambitious metrics before separating gross vs net, capacity, timeframe, leverage, turnover, fees, slippage, liquidity, and data leakage.
2. Never say no edge without a falsification test.
3. Separate impossible, unlikely, unproven, overfit, too small capacity, and not tested yet.
4. For Sharpe or CAGR claims, check sample size, volatility, drawdown, regime splits, turnover, exposure, leverage, costs, and out of sample behavior.
5. For options, check Greeks, IV/RV regime, assignment risk, liquidity, pin risk, gap risk, margin, fees, and execution assumptions.
6. Always propose the smallest experiment that could prove or disprove the edge.
7. Record evidence in the active Outcome Fusion session `proof.md`.

Default experiment list:

1. In sample vs out of sample.
2. Walk forward with frozen parameters.
3. Fee and slippage stress.
4. Remove best days or best trades.
5. Regime split.
6. Turnover and capacity check.
7. Alternative data source check.
8. Simpler baseline comparison.
