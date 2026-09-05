# RSI strategy backtest — results

**Date:** 2026-09-05
**Instrument:** BTC/USD daily, 3,170 bars, 2018-01-01 → 2026-09-05
**Source:** Alpha Vantage `DIGITAL_CURRENCY_DAILY` (5,895 bars back to 2010;
trimmed to 2018+ to skip the illiquid microcap era)
**Costs:** $20 spread per round trip, contract size 1, 0.01 lots, $10,000 start

## The answer

**The strategy loses money on this data, at every stop width and every
parameter combination tested.** Buy-and-hold made **+$656** over the same
window while the strategy lost between **-$255 and -$726**.

| Stop / target | Trades | Win rate | Profit factor | Net P/L | Buy & hold |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1% / 2% (your current setting) | 109 | 22.0% | 0.53 | **-$255** | +$656 |
| 3% / 6% | 103 | 24.3% | 0.69 | **-$263** | +$656 |
| 5% / 10% | 94 | 19.2% | 0.45 | **-$726** | +$656 |
| 8% / 16% | 79 | 26.6% | 0.64 | **-$576** | +$656 |

A profit factor below 1.0 means gross losses exceeded gross wins. Nothing here
is close to 1.0.

Worth noting about the 1%/2% row: average holding time was **1.0 bars**. A 1%
stop sits inside a single daily BTC candle, so almost every trade was stopped
out on the bar it opened. On the M15 bars the bot actually trades a 1% stop is
less absurd, but that is a reason to re-test on M15, not a reason to discount
the result — the wider stops lost more, not less.

## Parameter tuning does not rescue it

Tuned RSI period and thresholds on the first 70% of the data (2,219 bars), then
tested the winners on 951 bars they had never seen:

| RSI | Oversold | Overbought | In-sample P/L | Out-of-sample P/L |
| ---: | ---: | ---: | ---: | ---: |
| 14 | 20 | 80 | **+$21.51** | **-$124.49** |
| 21 | 25 | 75 | -$23.59 | -$197.13 |
| 7 | 30 | 70 | -$30.90 | -$508.32 |
| 7 | 25 | 75 | -$70.69 | -$18.01 |
| 21 | 20 | 80 | -$71.22 | -$60.53 |
| 14 | 25 | 75 | -$86.22 | -$195.43 |
| 21 | 30 | 70 | -$88.94 | -$146.94 |
| 14 | 30 | 70 | -$151.25 | -$111.40 |

Exactly one combination was profitable in sample. It lost $124 out of sample.
**Every one of the twelve combinations lost money on data it had not seen.**

This is the result that matters. If tuning had produced an out-of-sample winner
there would be something to investigate. It did not.

## Why the losses look structural

Win rate sits at 19–27% while the reward:risk is 2:1. At 2:1 you need to win
more than 33% of the time to break even before costs. The strategy is winning
about a quarter of its trades on a payoff that needs a third.

The mechanism is the one this design was always exposed to: RSI crossing back
up through 30 in a downtrend is a pause, not a reversal. The stop is hit on the
continuation. The optional EMA trend filter in `main.py` exists for exactly this
and was **not** part of these runs — testing it is the obvious next experiment.

## How the numbers were produced

`backtest.py` imports `compute_rsi` and `detect_signal` from `main.py` rather
than reimplementing them, so it measures the strategy that actually trades.

Fill assumptions, all pessimistic where there was a choice (`--explain` prints
these):

- **Entry** at the open of the bar *after* the signal bar. You cannot trade a
  close you have only just seen.
- **Both levels in one bar** → the **stop** is taken. Without tick data there is
  no way to know which came first, and assuming the win is how backtests lie.
- **Gap through the stop** → filled at the open, not the stop, modelling
  slippage.
- **Spread** charged once per round trip.
- **Not modelled:** swap/financing, commission, requotes, weekend gaps, and the
  chance your broker's feed differs from this data.

`test_backtest.py` verifies each of these against hand-computed values — 9 tests,
covering entry timing, target and stop fills, the both-levels case, gap
slippage, spread, contract scaling, and the zero-distance-stop guard.

## What this does and does not prove

**Does:** RSI(14) 30/70 mean reversion, long and short, with fixed
percentage stops, loses money on BTC daily bars over 8.5 years, and tuning its
parameters makes it worse out of sample.

**Does not:** say the same about M15 bars, which is what the bot is configured
for. Daily data was used because it was obtainable — Alpha Vantage's intraday
crypto endpoint is behind their paid tier. The M15 test needs history exported
from your own broker's terminal:

```
MT5 → View → Symbols → BTCUSD → Bars → export CSV
python backtest.py --csv BTCUSD_M15.csv --spread 20 --walk-forward
```

Also does not test: the EMA trend filter, ATR-scaled stops, session filters, or
any other symbol.

## Recommendation

Do not run this strategy on live money in its current form. The evidence says
it loses.

Before spending more on it, run the M15 test on your broker's own data — that is
the configuration you were about to trade, and it is one CSV export away. If M15
also loses, the honest conclusion is that plain RSI mean reversion has no edge
here, and the work is better spent on the parts of this project that do have
value: the safety layer, the daily loss guard, and this backtester, which just
did its job by saying no.
