# ORB (Strategy #1) optimizer - first real-data test

Data: Yahoo Finance 5-min regular-hours bars, QQQ/SPY/DIA, 2026-08-28 to 2026-11-20 (60 trading days, ~one trade/day).
Costs: 0.05R per trade. Split: first 36 days train (pick best of 27 unique variants), last 24 days test.
Script: artifacts/orb_optimizer.py (driver used the same trades()).

| Market | Baseline (opposite stop, exit at close) | Best variant picked on train | Train R | Test R (unseen) |
|---|---|---|---|---|
| QQQ | -14.6R, 35% win | mid stop + trail 0.5x range | +0.2 | +7.7 |
| SPY | -4.1R, 38% win | opposite stop + trail 1.0x range | +4.7 | +4.5 |
| DIA | -6.2R, 32% win | mid stop + trail 0.5x range | +1.8 | +8.4 |

Reading: the plain version lost on all three over this window; trailing-stop variants were positive on the unseen 24 days on all three. Consistent with the video's "the exit is the edge", but 24 test trades per market is far too few to trust.
Caveats: only ~3 months; one regime; no slippage beyond 0.05R; Yahoo data limited to 60 days. Needs multi-year data (premium feed) before any conclusion. Not financial advice.
