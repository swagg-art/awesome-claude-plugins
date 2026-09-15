# Limit orders instead of market orders — tested

**Date:** 2026-09-15
**Data:** USDCAD M15 2023–2025 (71,435 bars) and GBPUSD M15 2020 (24,915 bars)

Your suggestion, tested. It is the best idea anyone has had about this strategy:
it roughly halves the loss, and the improvement replicates out of sample on both
symbols. It still does not make the strategy profitable, and the reason why is
the most useful number in this whole project.

## Why it was worth testing — spread was most of the loss

Before building anything, the cost was measured directly:

| Spread | simple net | confirmed net |
| --- | ---: | ---: |
| 0.0 pips | **+6.94** | -220.91 |
| 0.5 pips | -61.63 | -215.99 |
| 1.0 pips | -122.35 | -242.47 |
| 2.0 pips | -251.27 | -365.33 |

1,087 trades × $0.20 of spread = **$217 of a $251 loss — 87%**. So the question
"can better execution fix this" was a real one, not a hunch.

## One correction to the premise

A limit order does **not** escape the spread. With a retail FX broker a buy
limit is a level on the *ask*, so the spread is paid either way. What it buys is
a **better entry level**, at the cost of missing every trade where price never
comes back.

That is still worth having for mean reversion, whose whole premise is that price
overshoots and returns — but the benefit is price improvement and selection, not
a cost saving. The results below are the honest version of the idea.

## It works

USDCAD M15, 2 pip spread:

| Entry | Trades | Win% | Profit factor | Net |
| --- | ---: | ---: | ---: | ---: |
| simple, market | 1,087 | 31.4 | 0.847 | -251.27 |
| simple, **limit 0.25 ATR** | 933 | 33.1 | 0.920 | -109.25 |
| simple, **limit 0.50 ATR** | 808 | 33.3 | **0.930** | **-82.69** |
| simple, limit 1.00 ATR | 600 | 32.0 | 0.867 | -119.71 |
| confirmed, market | 707 | 20.2 | 0.661 | -365.33 |
| confirmed, limit 0.25 ATR | 819 | 22.0 | 0.746 | -262.24 |
| confirmed, limit 0.50 ATR | 813 | 23.1 | 0.759 | -226.56 |
| confirmed, **limit 1.00 ATR** | 702 | 21.4 | **0.721** | **-180.62** |

The loss roughly halves on both strategies. Win rate rises. And unlike every
filter tried before, **the improvement replicates out of sample on both
symbols**:

| | full | in-sample | out-of-sample | out PF |
| --- | ---: | ---: | ---: | ---: |
| **USDCAD** simple, market | -251.27 | -135.54 | -115.72 | 0.752 |
| **USDCAD** simple, limit | **-82.69** | -5.64 | **-77.06** | **0.792** |
| **USDCAD** confirmed, market | -365.33 | -199.60 | -175.37 | 0.569 |
| **USDCAD** confirmed, limit | **-180.62** | -95.62 | **-84.99** | **0.633** |
| **GBPUSD** simple, market | -240.37 | -157.24 | -83.13 | 0.700 |
| **GBPUSD** simple, limit | **-137.11** | -95.95 | **-41.16** | **0.798** |

Note the confirmed strategy takes *more* trades on limit entry (819 vs 707).
Orders that expire unfilled free the position slot, so other setups get taken.

The one exception: confirmed + limit is worse on GBPUSD (-108 vs -41). The
simple strategy improves on both; the confirmed one does not.

## Why it still is not enough

Set the spread to **zero** — an impossible best case, with no cost of any kind:

| Config | Trades | Profit factor | Net | Per trade |
| --- | ---: | ---: | ---: | ---: |
| simple, market | 1,071 | 1.005 | +6.94 | **+$0.006** |
| simple, limit 0.5 ATR | 805 | 1.020 | +22.29 | **+$0.028** |
| confirmed, market | 735 | 0.774 | -220.91 | -$0.301 |
| confirmed, limit 1.0 ATR | 729 | 0.902 | -53.73 | -$0.074 |

**The gross edge is six-tenths of a cent per trade.** At 0.01 lots the spread
costs **$0.20** per trade. The edge is somewhere between 7x and 33x smaller than
the cost of trading, and the confirmed strategy has no gross edge at all — it
loses even for free.

This is the number that settles it. Execution improvements protect an edge; they
cannot create one. Limit orders recovered roughly half the spread cost, which is
real and worth keeping — but there is nothing underneath for them to protect.

To break even, gross profit would need to rise about 25% relative to gross loss.
No entry mechanic does that.

## What was built

`--entry limit` on the backtester, with `--limit-offset-atr` and
`--limit-expiry-bars`. Offsets are ATR multiples so they scale across
instruments. The suite now runs limit rows for both strategies as standard,
because execution turned out to matter more than any signal filter tried.

Fill modelling, pessimistic where there was a choice:

- **The order is anchored to the signal bar's close**, not the next bar's open.
  Anchoring to the open means a gap moves the order down with price, so you
  chase instead of being filled by the move you were waiting for. This was a
  genuine bug in the first implementation, caught by a test.
- **Price must trade *through* the level, not merely touch it.** A level touched
  once may not fill a retail order sitting at the back of the queue, and
  assuming it does is how limit backtests flatter themselves.
- **A gap past the level fills at the open**, which is better than the level.
  That is real, not optimism.
- **Unfilled orders expire** after `--limit-expiry-bars` and are counted, so the
  missed trades are visible rather than silently absent.

Six tests cover it, including that a touch does not fill and that market mode is
byte-for-byte unchanged.

## Conclusion

Your idea was right and it is now in the tool. It is the single biggest
improvement anything has made to these numbers — roughly half the loss, holding
out of sample on two symbols.

It does not rescue the strategy, and nothing else will, because at zero cost the
strategy makes six-tenths of a cent per trade. **The problem was never
execution. There is no edge.**

Keep limit entry for whatever gets built next. It is a genuine improvement to
how trades are taken. It just has nothing to work with here.
