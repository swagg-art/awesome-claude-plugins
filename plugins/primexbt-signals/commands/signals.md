---
description: Scan PrimeXBT instruments and output long/short/neutral signals with ATR-based entry, stop and targets
argument-hint: "[symbols...] (default: BTCUSD ETHUSD SOLUSD XRPUSD XAUUSD EURUSD)"
---

Use the `primexbt-signals` skill to produce a signals report for: $ARGUMENTS

If no symbols were given, use the skill's default watchlist. Fetch fresh daily
candles, run the signal engine, and present the table, reasoning, warnings, and
a 1%-risk position sizing example. Do not place any trades.
