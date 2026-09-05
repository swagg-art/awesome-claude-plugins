# Confirmed RSI strategy — what your changes did

**Date:** 2026-09-05
**Data:** BTC/USD daily, 3,170 bars, 2018-01-01 → 2026-09-05, $20 spread
**Your critique:** fixed SL/TP is wrong on a fluctuating chart; RSI needs
divergence and candlestick confirmation, not bare overbought/oversold; execution
should wait for confirmation rather than fire on a fixed threshold.

**Verdict on the critique: measurably correct.** Every part of it moved the
numbers, and the candlestick filter turned out to be the single most important
component in the whole strategy.

## Headline

| | v1 (threshold, fixed stops) | v2 (confirmed, structure stops) |
| --- | ---: | ---: |
| Profit factor | 0.533 | **1.193** |
| Net P/L | -$255 | **+$189** |
| Trades | 109 | 37 |
| Win rate | 22.0% | 29.7% |
| Average win | $12.14 | **$87.06** |
| Average hold | 1.0 bars | 27.4 bars |
| Profitable out of sample | **0 of 12** configs | **10 of 18** configs |

v1's average holding time of 1.0 bars is the fixed-stop problem you identified,
in one number: the stop was inside a single candle's normal range, so trades
died on the bar they opened. Structure-based stops let the same signal breathe
for 27 bars.

## Which change did the work

Each confirmation requirement removed in turn, everything else held constant
(divergence-only arming, 3R target, 5-bar window):

| Configuration | Trades | Win% | Profit factor | Net |
| --- | ---: | ---: | ---: | ---: |
| v1 baseline: threshold + fixed stops | 109 | 22.0 | 0.533 | -$255 |
| **All three confirmations required** | 37 | 29.7 | **1.193** | **+$189** |
| — without candle pattern | 42 | 14.3 | 0.317 | -$1,183 |
| — without close beyond prior bar | 59 | 23.7 | 0.402 | -$943 |
| — without RSI turning | 37 | 29.7 | 1.193 | +$189 |
| — candle pattern alone | 60 | 23.3 | 0.403 | -$938 |
| — no confirmation at all | 49 | 20.4 | 0.511 | -$714 |

Three things fall out of this:

1. **The candlestick filter is the strategy.** Remove it and profit factor
   collapses from 1.19 to 0.32 — worse than doing nothing. This was your
   specific suggestion and it carries the result.
2. **Pattern and momentum are both needed, and neither works alone.** Pattern
   without the close-beyond-prior-bar gives 0.40. The break without the pattern
   gives 0.32. Together, 1.19. They are not additive; they are a conjunction.
3. **The RSI-turning check is redundant.** Removing it changes nothing — same 37
   trades, same P/L. It is implied by the other two. Left in as a switch, but it
   earns nothing.

**Setup funnel:** 150 setups armed, 37 confirmed, 112 expired unfilled — **75%
discarded**. That is "wait for confirmation, do not fire on a threshold" doing
exactly what you said it should.

## Out-of-sample — the honest part

Tuned on 2018-01 → 2024-01, tested on 2024-01 → 2026-09 (951 unseen bars):

| Div only | Reward | Confirm | In-sample net | In PF | Out net | Out PF |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| No | 3.0 | 10 | +$343 | 1.56 | **-$520** | 0.36 |
| Yes | 3.0 | 10 | +$268 | 1.51 | -$589 | 0.20 |
| Yes | 3.0 | 3 | +$217 | 1.67 | -$4 | 0.99 |
| Yes | 3.0 | 5 | +$121 | 1.26 | **+$149** | 1.35 |
| No | 3.0 | 5 | +$40 | 1.06 | +$126 | 1.24 |
| Yes | 1.5 | 3 | -$48 | 0.91 | +$118 | 1.43 |

**v1: 0 of 12 configurations were profitable out of sample. v2: 10 of 18.**
That shift is the real finding.

But note the top row: the best in-sample configuration still lost $520 out of
sample. **Picking parameters by in-sample performance still fails**, even with a
better strategy. And out-of-sample trade counts are 6–14 — far too few to call
any single row an edge.

## What I am and am not claiming

**Claiming:** your three changes are a genuine, measured improvement. Profit
factor better than doubled, out-of-sample survival went from never to about half
the time, and the ablation isolates candlestick confirmation as the reason.

**Not claiming:** that this is a tradable edge. 37 trades over 8 years is a small
sample. The out-of-sample windows hold single-digit trade counts. Daily bars are
not the M15 the bot is configured for. And I selected the 3R/5-bar settings
after looking at the data, which is the same sin the walk-forward table exists
to expose.

## What is now in the code

`strategy.py` — pure functions, no broker dependency:

- **Candlestick patterns:** bullish/bearish engulfing, hammer, shooting star,
  piercing line, dark cloud cover, morning star, evening star. Thresholds are
  ratios of each candle's own range, so they mean the same thing on BTC at
  $64,000 and EURUSD at 1.08.
- **Swing structure:** pivot highs and lows. A pivot needs `right` bars after it
  to be confirmed, so the newest pivot is always a few bars old — that lag is
  real, and pretending otherwise reads the future.
- **Regular divergence:** price lower low with RSI higher low (bullish), and the
  mirror. Never reads past the current bar; there is a test for that.
- **`levels_from_structure`:** stop behind the swing plus an ATR buffer, target
  as a multiple of that distance. A quiet chart gives a near stop and near
  target; a wild one gives both far away.

`STRATEGY=confirmed` is the default in `.env.example`. `STRATEGY=simple` still
runs the original for comparison.

**Verification:** 35 tests. 26 in `test_strategy.py` cover every pattern against
hand-built candles, divergence detection including a lookahead guard, and the
level arithmetic. 9 in `test_backtest.py` cover fill mechanics. Both strategies
now run through **one** shared fill engine, so they are measured identically.

I also replayed `main.evaluate_confirmed` — the live decision path — bar by bar
over the same data and compared it against the backtester: **37 of 37 entries
reproduced, sides matching**. The bot trades what was measured.

## Next, in order of value

1. **M15 data from your broker.** This is still daily. One CSV export settles
   whether any of this holds on the timeframe you actually trade.
   `python backtest.py --csv BTCUSD_M15.csv --walk-forward`
2. **More symbols.** An edge that exists only on BTC is probably not an edge.
3. **Drop the RSI-turn check.** It is measurably doing nothing.
4. **Do not tune further on this data.** The walk-forward table shows where that
   leads.
