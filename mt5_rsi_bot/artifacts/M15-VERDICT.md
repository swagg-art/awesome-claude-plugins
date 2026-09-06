# The M15 test, on real broker-grade data — the strategy does not work

**Date:** 2026-09-06
**Data:** HistData.com M1, resampled to M15
**Instruments:** USDCAD 2023–2025 (71,435 M15 bars) and GBPUSD 2020 (24,915 bars)

This is the test the whole project was waiting on. Every earlier result rested
on 3,170 daily BTC bars producing 37 trades. This one produces **1,087**.

The answer is no.

## USDCAD, three years, 71,435 M15 bars

Spread 2 pips. P/L in CAD (the quote currency) — divide by about 1.36 for USD.

| Strategy | Trades | Win% | Profit factor | Net | Max DD% |
| --- | ---: | ---: | ---: | ---: | ---: |
| simple (threshold, fixed stops) | 1,087 | 31.4 | 0.847 | **-251.27** | 2.72 |
| confirmed (config default) | 707 | 20.2 | 0.661 | **-365.33** | 3.82 |
| confirmed, divergence-only | 603 | 18.2 | 0.552 | **-455.47** | 4.76 |
| confirmed + EMA 50 | 235 | 23.4 | 0.809 | **-94.83** | 1.14 |
| confirmed + EMA 100 | 227 | 22.0 | 0.659 | **-164.14** | 1.68 |
| confirmed + EMA 200 | 271 | 22.9 | 0.648 | **-177.53** | 1.93 |
| confirmed, long only | 529 | 21.6 | 0.819 | **-138.94** | 1.64 |

**Every variant loses.** No profit factor reaches 1.0. Walk-forward at 70/30 is
negative in *both* halves for every variant tested:

| Variant | In-sample | Out-of-sample |
| --- | ---: | ---: |
| confirmed (default) | -199.60 | -175.37 |
| confirmed, divergence-only | -303.79 | -159.58 |
| confirmed + EMA 100 | -137.24 | -31.39 |
| confirmed, long only | -36.71 | -107.37 |
| simple | -135.54 | -115.72 |

## GBPUSD 2020, 24,915 M15 bars — an independent check

| Strategy | Trades | PF | Net |
| --- | ---: | ---: | ---: |
| simple | 614 | 0.734 | -240.37 |
| confirmed (default) | 374 | 0.946 | -40.74 |
| confirmed, divergence-only | 269 | 0.808 | -126.15 |
| confirmed + EMA 50 | 126 | 0.584 | -185.68 |
| confirmed + EMA 100 | 98 | 0.735 | -90.49 |
| confirmed + EMA 200 | 127 | 1.071 | **+21.43** |
| confirmed, long only | 240 | 1.014 | **+6.47** |

Two variants came out barely positive. Neither survives inspection:

**It is spread, not edge.** The EMA 200 result decays straight to zero as costs
become realistic:

| Spread | Trades | PF | Net |
| --- | ---: | ---: | ---: |
| 1.0 pip | 127 | 1.082 | +24.42 |
| 1.5 pips | 127 | 1.071 | +21.43 |
| 2.0 pips | 127 | 1.031 | +9.45 |
| 2.5 pips | 127 | 1.020 | +6.24 |
| 3.0 pips | 127 | 1.009 | +2.99 |

At a realistic retail spread the whole year makes **$3** across 127 trades — two
cents a trade. Slippage, a wider spread during news, or one bad fill erases it.

**And it does not replicate.** The filter that was least-bad on USDCAD was
EMA 50. The one that "won" on GBPUSD was EMA 200 — which lost $177 on USDCAD.
A parameter that flips between symbols is fitted noise, not a mechanism.

## What this overturns

The BTC daily result — 37 trades, PF 1.193, +$189 — looked like the project's
one piece of good news. Against 1,087 trades saying the opposite, it was a
small sample. 37 trades is roughly what you get from flipping a coin 37 times
and finding a run.

That earlier report said the result was "necessary, not sufficient" and needed
confirming on a real sample. It has now been confirmed the other way.

## Two bugs found running it

**The backtester was quadratic.** `arm_setup` rebuilt both price columns from
the DataFrame on every bar, and `find_divergence` scanned the entire history
from bar 0 before discarding every pivot outside a 60-bar lookback. Both are
O(n) per bar, so the full run was heading for hours. Now the divergence scan
covers only the window that survives and the columns are hoisted out of the
loop: **8,000 bars went from 2.87s to 1.03s, and per-bar cost stopped growing
with dataset size.** Verified behaviour-preserving — `find_divergence` was
compared bar by bar against the old implementation across 15,960 calls with
**zero mismatches**.

**The verdict overclaimed.** When the best full-sample variant was not among the
walk-forward rows, the summary fell through to "Positive in and out of sample"
— asserting out-of-sample evidence that did not exist. It now says plainly that
the variant was never split-tested. This bug produced exactly the false
confidence the tool is meant to prevent, on the one line most likely to be read.

## The honest conclusion

RSI mean reversion — as a bare threshold cross, and with divergence plus
candlestick confirmation and structure stops — **does not have an edge on M15
FX.** Not on 71,435 bars of USDCAD across three years, and not on a year of
GBPUSD.

Do not trade it. Do not tune it further: twelve BTC parameter combinations were
already all negative out of sample, and here every variant is negative on both
halves of a sample thirty times larger.

## What the project is actually worth

The strategy is worthless. The tooling is not:

- **The backtester** gives an honest answer in 100 seconds over 71,435 bars,
  with pessimistic fills, walk-forward built in, and verified arithmetic. It
  just did the single most valuable thing it could — said no before any money
  moved.
- **The safety layer** in `mt5_rsi_bot` — daily loss guard, stop sanity checks,
  the refusal to start on a two-dollar stop.
- **`liquid_assistant`** — position sizing that keeps liquidation beyond the
  stop.
- **`native-mt5`** — the MCP server.

Anything built next should be measured with this pipeline before it is trusted.
That is the durable result here.
