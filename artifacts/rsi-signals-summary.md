# RSI Signals — Summary Report

**Date:** 2026-09-07
**Branch:** `claude/rsi-signal-codes-qdcfnv`
**Deliverable:** dependency-free RSI indicator + signal engine, tests, CLI, docs.

## What was asked

Code for RSI signals. The repository is a Next.js plugin catalog with no trading
code in it, so this landed as a self-contained top-level `rsi/` package rather
than being wired into the app. CI only builds `ui/`, so nothing existing is
affected.

## What was built

| File | Lines | Purpose |
|---|---|---|
| `rsi/rsi_signals.py` | ~700 | Indicator, streaming class, 5 signal rules, scorer, CLI |
| `rsi/positions.py` | ~600 | ATR, three exit families, trade simulation, statistics, CLI |
| `rsi/test_rsi_signals.py` | ~250 | 25 unittest cases, no network, no fixtures |
| `rsi/test_positions.py` | ~300 | 33 cases: fills, every exit condition, statistics |
| `rsi/README.md` | ~190 | Usage, rule reference, exit model, tuning, caveats |
| `rsi/sample_prices.csv` | 300 rows | Synthetic daily bars for a runnable demo |

Python 3.8+, standard library only — no numpy, no pandas. It drops into a
backtest script, a bot loop, or an MCP tool wrapper unchanged.

### Indicator

* `rsi(closes, period=14, method="wilder"|"sma")` — output aligned 1:1 with
  input, `None` while warming up.
* `StreamingRsi` — O(1) memory and O(1) per bar for live feeds; proven in tests
  to match the batch computation to 9 decimal places.
* `stoch_rsi(...)` — %K / %D.

### Signal rules (five, independently toggleable)

1. **Threshold exits** — buy the cross back *above* oversold, sell the cross back
   *below* overbought. Mean reversion.
2. **Centerline crosses** — the 50 line as a momentum regime switch. Trend
   following, off by default.
3. **Divergence** — price lower low / RSI higher low, and the mirror image.
4. **Failure swings** — Wilder's own preferred rule; reads RSI's structure only,
   ignores price.
5. **StochRSI crosses** — early and noisy, off by default.

Post-processing: strength scoring (0–1) and a same-direction cooldown so one
wobble around a band does not become five entries.

### Correctness evidence

* RSI matches **Wilder's published worked example** from *New Concepts in
  Technical Trading Systems* to within 0.01 across all 19 reference values
  (70.46, 66.25, 66.48, … 33.09, 37.79).
* 58 tests pass: reference values, alignment, saturation (100/0/50) edges,
  streaming-vs-batch equivalence, signal ordering, no-lookahead, cooldown
  behaviour, band selectivity, CSV parsing (case-insensitivity, newest-first
  auto-reversal, malformed rows), plus fill delay, every exit condition,
  cost accounting, MAE/MFE, and the summary statistics.

## Design decisions worth knowing

* **No lookahead.** Every signal is stamped with the first bar it could actually
  be taken on. Divergences are dated `pivot_window` bars *after* the pivot,
  because a pivot is not confirmed until then. Most published divergence code
  dates the signal at the pivot itself, backdating every entry by a few bars and
  flattering the backtest.
* **Exit, not entry.** Threshold signals fire on the cross back out of a band.
  Buying the first print below 30 means buying every step of a downtrend.
* **Bands are the trend defence.** 70/30 fades extremes and loses in strong
  trends; the README documents shifting to 80/40 (uptrend) or 60/20 (downtrend)
  instead of adding a filter.
* **The scorer is not a backtest.** `evaluate_signals` gives forward-return hit
  rates with no costs, slippage, sizing, or overlap handling — a screen for
  parameter sets, labelled as such so it is not mistaken for a result.

## Demo run (synthetic sample, 300 bars)

```
rsi/sample_prices.csv: 300 bars, last close 126.5
RSI(14,wilder) = 60.01  [neutral]

8 signals
   bar  date         side    rsi      price   str  source
    19  2025-01-29   SELL   69.9      108.1  0.51  overbought_exit
    72  2025-04-14   SELL   69.5      131.3  0.61  overbought_exit
    81  2025-04-25   SELL   52.6        129  0.68  bearish_failure_swing
   115  2025-06-12   BUY    44.9      120.2  0.59  bullish_divergence
   147  2025-07-28   BUY    48.5      117.8  0.57  bullish_divergence
   191  2025-09-26   SELL   60.0      123.4  0.51  overbought_exit
   195  2025-10-02   SELL   59.6      123.9  0.61  bearish_failure_swing
   245  2025-12-11   SELL   67.5      128.3  0.55  bearish_divergence
```

Those hit rates are from 300 bars of synthetic random-walk data. They say the
plumbing works; they say nothing about whether the rules make money.

## Exits (added after review)

The first cut emitted signals with no position management: a later contrary
signal was another independent signal, not a close. `rsi/positions.py` walks a
signal stream into round-trip trades under an explicit `ExitPolicy`. Three
families, freely combinable — whichever fires first wins, in the order stop,
target, trailing stop, RSI level, time stop, opposite signal.

| Preset | Exits armed | Behaviour |
|---|---|---|
| `opposite_signal()` | contrary signal | Stays in trends, gives back a lot at turns |
| `rsi_level()` | RSI level (50 default) + contrary | Banks the mean reversion; no floor under losses |
| `risk()` | ATR stop, ATR target, contrary | Risk decides the exit; RSI only picks the entry |
| `combined()` | all of the above + trail + time stop | Hard limits with an RSI take-profit |

Execution model: fills are delayed one bar (a signal from bar *n*'s close cannot
trade at that close); stops fill at their level only when highs/lows are given,
otherwise at the breaching bar's close; a bar spanning both stop and target is
assumed to hit the stop; no pyramiding; `cost_bps` charged per side.

**One guard worth naming.** If a stop is armed but ATR is unusable at the fill
bar — during warm-up, or on a dead-flat stretch — the entry is skipped rather
than taken without a stop. A test caught the original behaviour opening an
unprotected position and running it to the end of the data.

### Why the exit matters more than the entry

Same eight signals through all four policies on the sample data:

```
opposite    3 trades  win 0.333  total -0.0848  max dd -0.1055
rsi-level   6 trades  win 0.667  total -0.1202  max dd -0.1789
risk        7 trades  win 0.429  total -0.0149  max dd -0.0669
combined    7 trades  win 0.286  total -0.0235  max dd -0.0703
```

`rsi-level` wins two thirds of its trades and finishes worst: one short was held
62 bars for −17.4% waiting for RSI to return to 50 while price trended away.
Nothing in that policy can cut a loser — which is what the stop in `risk` and
`combined` exists to do. Synthetic data: it demonstrates the mechanism, not an
edge.

## Limitations

* Signal rules are close-only. `positions.py` accepts highs/lows for ATR and
  stop fills, but the pivot detection behind divergence still ignores wicks.
* No position sizing — every trade is one unit, sequential, single instrument.
* No slippage model, partial fills, or funding/overnight cost.
* Divergence pivot detection uses a fixed symmetric window; adaptive
  (volatility-scaled) pivots would be better on mixed-regime data.

## Possible next steps

* TypeScript port, to sit alongside the existing `ui/` code.
* Wick-based pivots for divergence, now that OHLC flows through the exit layer.
* Wire to the Alpha Vantage MCP `RSI`/`TIME_SERIES_DAILY` tools for live symbols
  (the CLI already has a direct HTTP path via `--symbol`).
* A proper event-driven backtest with costs, to replace the scorecard.

## Verification

```
$ python3 -m unittest discover -s rsi -p "test_*.py"
Ran 58 tests in 0.016s
OK
```
