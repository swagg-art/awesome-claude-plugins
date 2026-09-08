# RSI signals

Relative Strength Index and the signal rules built on top of it, in one
dependency-free Python module (`rsi_signals.py`, stdlib only, Python 3.8+).

```bash
python3 rsi/rsi_signals.py --csv rsi/sample_prices.csv            # table
python3 rsi/rsi_signals.py --csv rsi/sample_prices.csv --json     # machine readable
python3 rsi/rsi_signals.py --symbol AAPL                          # ALPHAVANTAGE_API_KEY
python3 -m unittest discover -s rsi -p "test_*.py"                # 58 tests
```

## Library use

```python
from rsi.rsi_signals import rsi, generate_signals, evaluate_signals, RsiConfig

values  = rsi(closes, period=14)                  # aligned to closes; None while warming
signals = generate_signals(closes, dates, RsiConfig(oversold=30, overbought=70))
report  = evaluate_signals(closes, signals, horizon=5)

for s in signals[-5:]:
    print(s.timestamp, s.direction, s.source, round(s.rsi, 1), s.note)
```

Live bars, without recomputing history each tick:

```python
from rsi.rsi_signals import StreamingRsi

streamer = StreamingRsi(period=14)
for bar in feed:                      # O(1) per update
    value = streamer.update(bar.close)   # None until 15 bars have arrived
```

## The indicator

`rsi(closes, period=14, method="wilder")` returns a list the same length as
`closes`, with `None` for the first `period` bars.

* **wilder** (default) - Wilder's smoothing, the standard used by TradingView,
  Alpha Vantage and most brokers. Verified against Wilder's own worked example
  from *New Concepts in Technical Trading Systems* to within 0.01.
* **sma** - Cutler's RSI, a plain rolling average. Not path dependent, so two
  people with different history lengths get the same number.

Edge cases: all-gains -> 100, all-losses -> 0, flat -> 50.

## The five signal rules

| Rule | Fires | Direction | Character |
|---|---|---|---|
| `oversold_exit` / `overbought_exit` | RSI crosses back *out* of a band | buy / sell | mean reversion |
| `centerline_cross_up` / `_down` | RSI crosses 50 | buy / sell | trend following (off by default) |
| `bullish_divergence` / `bearish_divergence` | price makes a lower low / higher high, RSI does not | buy / sell | reversal, earliest and most fragile |
| `bullish_failure_swing` / `bearish_failure_swing` | RSI holds the band and breaks its own swing point | buy / sell | Wilder's own preferred rule |
| `stochrsi_cross_up` / `_down` | %K crosses %D at an extreme | buy / sell | early, noisy (off by default) |

Waiting for the *exit* from a band rather than entry is deliberate: buying the
first print below 30 means buying every step of a downtrend. The failure-swing
rules are price independent - they read only RSI's own structure - which is why
Wilder rated them above the band crossings.

Each `Signal` carries `index`, `timestamp`, `direction`, `source`, `rsi`,
`price`, `strength` (0-1 heuristic) and a human-readable `note`.

## Timing and lookahead

Every signal is stamped with the first bar on which it could actually be taken,
using only closed-bar data up to that index:

* Threshold, centerline, failure-swing and StochRSI signals fire on the close of
  the crossing bar - tradeable at the next open.
* Divergence signals fire `pivot_window` bars *after* the pivot they rely on,
  because a pivot is not confirmed until that many bars have printed. Most
  divergence code dates the signal at the pivot itself, which quietly backdates
  every entry by a few bars and flatters any backtest.

`cooldown_bars` (default 3) drops same-direction repeats that fire within N bars
of the previous one, so one wobble around a band does not become five entries.

## Tuning

`RsiConfig` holds every knob. The ones that matter:

* `period` - 14 is standard; 7 is roughly twice as busy, 21 roughly half.
* `overbought` / `oversold` - **the main defence against trends.** 70/30 fades
  extremes, which loses money in a strong trend. Shift the bands with the trend
  instead: 80/40 in an uptrend, 60/20 in a downtrend.
* `use_centerline` - turn on for trend following, off for mean reversion. Running
  both at once produces contradictory signals by construction.
* `pivot_window` - larger means fewer, better-confirmed divergences, dated later.

## Scoring

`evaluate_signals` reports hit rate and average move in the signal's direction
over the next N bars, overall and per rule. It is a sanity check on a parameter
set, **not a backtest**: no costs, no slippage, no position sizing, no overlap
handling. A rule that fails here is not worth backtesting properly; passing here
means little on its own.

`summarize_trades` in `positions.py` goes further - win rate, profit factor,
expectancy, max drawdown on compounded equity, and MAE/MFE per trade - but the
same caveat holds: single instrument, sequential trades, no slippage model.

RSI is a momentum oscillator, not a forecast. In a trending market it can sit
pinned above 70 for weeks while price keeps rising - "overbought" is not "about
to fall". Treat these signals as one input alongside trend and risk limits.

## Exits

`rsi_signals` says when momentum is interesting. It does **not** manage a
position - a later contrary signal is another independent signal, not a close.
`positions.py` closes that gap: it walks a signal stream into round-trip trades
under an explicit `ExitPolicy`.

```bash
python3 rsi/positions.py --csv rsi/sample_prices.csv --exit all
python3 rsi/positions.py --csv rsi/sample_prices.csv --exit risk --cost-bps 5
```

```python
from rsi.positions import ExitPolicy, simulate, summarize_trades

trades = simulate(closes, signals, ExitPolicy.combined(), highs=highs, lows=lows)
print(summarize_trades(trades)["profit_factor"])
```

Three families, freely combinable - **whichever condition fires first wins**,
in the order stop, target, trailing stop, RSI level, time stop, opposite signal:

| Preset | Exits armed | Behaviour |
|---|---|---|
| `ExitPolicy.opposite_signal()` | contrary signal | Stays in trends, gives back a lot at turns. `reverse=True` flips instead of flattening |
| `ExitPolicy.rsi_level()` | RSI reaching a level (50 default), contrary signal | Banks the mean reversion. High win rate, no floor under the losses |
| `ExitPolicy.risk()` | ATR stop, ATR target, contrary signal | Risk decides the exit; RSI only picks the entry. Add `trail_atr` or `time_stop_bars` |
| `ExitPolicy.combined()` | all of the above | Hard risk limits, an RSI take-profit, a contrary signal as backstop |

Every field is independent, so the presets are only starting points -
`ExitPolicy(stop_atr=1.5, rsi_exit_long=60, on_opposite_signal=False)` is as
valid as any of them. `armed()` lists what a policy can actually do.

### Execution model

* **Fills are delayed.** A signal computed from bar *n*'s close cannot trade at
  bar *n*'s close, so entries fill at `entry_delay_bars` later (default 1) at
  that bar's close.
* **Stops fill at their level only with OHLC.** Pass `highs=`/`lows=` and a
  breached stop fills at the stop price; with closes only it fills at the close
  of the breaching bar. When one bar spans both stop and target, the stop is
  assumed first.
* **No pyramiding.** One position at a time; same-direction signals during a
  position are ignored.
* **No unprotected risk trades.** If a stop is armed but ATR is unusable at the
  fill bar (warm-up, or a dead-flat stretch), the entry is skipped rather than
  taken without a stop. Opt out with `require_atr_for_risk_exits=False`.
* **Costs.** `cost_bps` is charged per side; `Trade` carries both
  `gross_return` and `net_return`.
* A position still open at the end is closed at the last bar with
  `exit_reason="end_of_data"`, and `summarize_trades` counts those separately.

### What the sample data shows

Running `--exit all` over the bundled 300 bars is a good illustration of why
the exit choice matters more than the entry:

```
opposite    3 trades  win 0.333  total -0.0848  max dd -0.1055
rsi-level   6 trades  win 0.667  total -0.1202  max dd -0.1789
risk        7 trades  win 0.429  total -0.0149  max dd -0.0669
combined    7 trades  win 0.286  total -0.0235  max dd -0.0703
```

Same eight signals in every row. `rsi-level` wins two thirds of its trades and
still finishes worst: one short was held 62 bars for -17.4% waiting for RSI to
come back to 50 while price trended away from it. Nothing in that policy can
cut a loser, which is exactly what the stop in `risk` and `combined` is for.
(Synthetic data - it demonstrates the mechanism, not an edge.)

## Files

| File | |
|---|---|
| `rsi_signals.py` | indicator, streaming class, five rules, scorer, CLI |
| `positions.py` | ATR, exit policies, trade simulation, statistics, CLI |
| `test_rsi_signals.py` | 25 tests, incl. Wilder's reference values |
| `test_positions.py` | 33 tests covering fills, every exit, and the statistics |
| `sample_prices.csv` | 300 synthetic daily bars for a runnable demo |
