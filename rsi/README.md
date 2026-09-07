# RSI signals

Relative Strength Index and the signal rules built on top of it, in one
dependency-free Python module (`rsi_signals.py`, stdlib only, Python 3.8+).

```bash
python3 rsi/rsi_signals.py --csv rsi/sample_prices.csv            # table
python3 rsi/rsi_signals.py --csv rsi/sample_prices.csv --json     # machine readable
python3 rsi/rsi_signals.py --symbol AAPL                          # ALPHAVANTAGE_API_KEY
python3 -m unittest discover -s rsi -p "test_*.py"                # 25 tests
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

RSI is a momentum oscillator, not a forecast. In a trending market it can sit
pinned above 70 for weeks while price keeps rising - "overbought" is not "about
to fall". Treat these signals as one input alongside trend and risk limits.

## Files

| File | |
|---|---|
| `rsi_signals.py` | indicator, streaming class, five rules, scorer, CLI |
| `test_rsi_signals.py` | 25 tests, incl. Wilder's reference values |
| `sample_prices.csv` | 300 synthetic daily bars for a runnable demo |
