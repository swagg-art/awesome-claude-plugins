# EMA trend filter — tested, and it makes things worse

**Date:** 2026-09-05
**Data:** BTC/USD daily, 3,170 bars, 2018-01-01 → 2026-09-05, $20 spread
**Baseline:** the v2 confirmed strategy (divergence-armed, candlestick +
break + RSI-turn confirmation, structure stops, 3R target, 5-bar window),
reproduced exactly at 37 trades / PF 1.193 / +$188.87 before any change.

## The answer

**Do not enable it.** The EMA trend filter costs money at every period tested,
and combining it with long-only produces a 0% win rate.

| Variant | Trades | Win% | Profit factor | Net | Max DD% |
| --- | ---: | ---: | ---: | ---: | ---: |
| **Baseline (no filter)** | 37 | 29.7 | **1.193** | **+$188.87** | 5.30 |
| EMA 50 | 12 | 25.0 | 0.688 | -$172.08 | 3.59 |
| EMA 100 | 9 | 22.2 | 0.796 | -$84.28 | 2.60 |
| EMA 200 | 8 | 12.5 | 0.226 | -$338.89 | 4.38 |
| Long only | 24 | 29.2 | 0.963 | -$31.31 | 5.06 |
| EMA 100 + long only | 6 | 0.0 | n/a | -$340.68 | 3.41 |
| EMA 200 + long only | 6 | 0.0 | n/a | -$390.89 | 3.91 |

Walk-forward, split 70/30 (no tuning — the same fixed settings on both halves):

| Variant | In-sample trades | In-sample net | Out-of-sample trades | Out-of-sample net |
| --- | ---: | ---: | ---: | ---: |
| **Baseline** | 29 | **+$120.98** | 7 | **+$148.90** |
| EMA 50 | 8 | +$52.46 | 3 | -$143.58 |
| EMA 100 | 6 | +$59.30 | 3 | -$205.25 |
| EMA 200 | 5 | -$195.31 | 3 | -$205.25 |
| Long only | 18 | -$128.90 | 6 | +$97.60 |
| EMA 100 + long only | 4 | -$98.32 | 2 | -$242.36 |
| EMA 200 + long only | 4 | -$148.53 | 3 | -$295.16 |

The baseline is the only variant positive in both halves.

## Why it fails — the filter removes the winners

The filter is not neutral. It is systematically cutting the profitable trades:

| Filter | Trades kept | Trades removed | Aggregate P/L of what was removed |
| --- | ---: | ---: | ---: |
| EMA 50 | 12 | 25 | **+$360.96** (+$14.44 each) |
| EMA 100 | 9 | 28 | **+$273.15** (+$9.76 each) |
| EMA 200 | 8 | 29 | **+$527.77** (+$18.20 each) |

The mechanism is straightforward once seen. A divergence-confirmed reversal
fires *while price is still on the wrong side of the EMA* — that is what
catching a turn means. Requiring price to have already crossed back over the
EMA means waiting until the reversal has largely happened, so the filter keeps
the late entries and discards the good ones.

This is the opposite of the hypothesis in the previous report, which blamed
v1's losses on buying into downtrends. That diagnosis was right about v1's
bare threshold cross. It is wrong about v2: the divergence and candlestick
confirmation **is already** the trend-reversal evidence, so bolting an EMA on
top filters the signal twice and keeps the worse half.

## The long-only trap

Shorts look like the problem. In the baseline they are not profitable:

| Side | Trades | Wins | Net |
| --- | ---: | ---: | ---: |
| BUY | 18 | 6 (33%) | **+$269.72** |
| SELL | 19 | 5 (26%) | **-$80.84** |

The obvious inference — drop the shorts and keep +$270 — is **wrong**, and the
data says so: long-only returns -$31.31, not +$269.72.

The reason is position occupancy. The strategy holds one position at a time, so
while it is in a short it cannot arm and confirm anything else. Remove the
shorts and those bars come free:

| | Trades | Net |
| --- | ---: | ---: |
| The 18 longs the baseline also took | 18 | +$269.72 |
| 6 extra longs, taken while the baseline was holding a short | 6 | **-$301.02** |
| Long-only total | 24 | -$31.31 |

Being stuck in a losing short was, on this data, cheaper than being free to take
the next long. **You cannot evaluate a subset of trades in isolation when the
strategy can only hold one position at a time.** Any future "just remove the
losing subset" idea needs re-running end to end, not arithmetic on a trade list.

## Caveats, which are large

- **Sample sizes are small and the filtered ones are tiny.** 8–12 trades tells
  you almost nothing. The direction of the result is consistent across every
  period and both halves, which is what makes it worth acting on, but no single
  filtered row is individually significant.
- **The baseline's out-of-sample is 7 trades.** +$148.90 on 7 trades is not
  proof the baseline works either. It is the best of the options tested, which
  is a much weaker claim.
- **Daily bars, one symbol.** The bot is configured for M15. Still untested
  there, because Alpha Vantage's intraday crypto endpoint is paid — it needs a
  CSV exported from your own terminal.

## What was built

`passes_trend_filter(action, price, trend, long_only=False)` in `strategy.py` —
pure, and shared by the live bot and the backtester so they cannot drift apart.
Wired into both the `simple` path (`detect_signal`) and the `confirmed` path
(`ConfirmedStrategy.decide` and `evaluate_confirmed`).

Config: `EMA_TREND_PERIOD` (0 = off, the default) and `LONG_ONLY` (false by
default). Both stay off, because that is what the measurement says.

Seven tests in `test_strategy.py` cover the filter, including the case that
matters most: a NaN EMA during warm-up must let signals through rather than
silently blocking every trade for the first 200 bars.

## Recommendation

Leave `EMA_TREND_PERIOD=0` and `LONG_ONLY=false`. The filter is implemented,
tested, and available if a different symbol or timeframe behaves differently —
but on this data it destroys the edge the confirmation logic built.

The open question is still M15 on your broker's own history. That remains the
one test that would change what the bot should actually do.
