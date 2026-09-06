# Indicators cross-checked against an independent source

**Date:** 2026-09-06
**Source:** Liquid (via the Co-Invest connector), `get_technical_indicators`

Every result in this project depends on `compute_rsi` and `average_true_range`
being right. Until now they were checked against Wilder's published example and
against hand-computed cases — good, but both are my own arithmetic. Liquid
computes the same indicators independently, on its own price feed, so it is a
genuine outside check.

## Result

BTC daily, 810 candles:

| Indicator | Ours | Liquid | Difference |
| --- | ---: | ---: | ---: |
| RSI(14) | 66.43 | 66.71 | **-0.28** |
| ATR(14) | 2,370.45 | 2,415.99 | -45.54 (1.9%) |

Both differences are explained by the inputs, not the maths:

- **Different venue.** Our last daily close is 79,659 (Alpha Vantage); Liquid's
  price at the time of the call was 79,804. A $145 gap in the most recent close
  moves a 14-period RSI by roughly this much.
- **Liquid's last candle was still forming** (`latestCandleForming: true`),
  so it is comparing a partial bar against our completed one.

A 0.28 gap on RSI is agreement. For contrast, `pandas-ta` — which this project
dropped — computes RSI with an unseeded EWM and returned **50.66** where
Wilder's published value is 70.5 on his own test series. That is the difference
between an implementation that agrees with the chart and one that does not.

## Incidental confirmations

- **The daily BTC history used for every backtest is real and current.** Our
  2026-09-05 close of 79,659 sits within 0.2% of Liquid's live price. The data
  behind the -$255 v1 result and the +$189 v2 result is sound.
- **The repainting hazard is real, not theoretical.** Liquid explicitly flags
  `latestCandleForming: true`. That is precisely the bar the original bot read
  its signal from, via `df['rsi'].iloc[-1]`, and which this project now drops.
  An independent data provider considers it important enough to label.

## What Liquid cannot do

It returns *computed indicator values and live prices*, not candle series.
`show_chart` caps at 200 candles — about two days at M15. A backtest needs
thousands of bars, so the M15 question still needs a downloaded file.

Where it is genuinely useful: live data and sanity checks for a running bot, and
exactly this kind of independent verification.
