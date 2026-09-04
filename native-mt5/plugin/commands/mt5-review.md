---
description: Review the connected MT5 account — exposure, risk and recent performance.
---

Produce a short account review using the Native MT5 tools. Do not place, modify
or close anything; this command is read-only regardless of the server's mode.

1. Call `mt5_status` and state plainly which account and mode you are attached
   to. If the mode is `live`, say so in the first line.
2. Call `mt5_account` and report balance, equity, free margin and margin level.
   Flag a margin level under 200% as a warning.
3. Call `mt5_positions`. For each position give symbol, side, volume, entry,
   current price and floating P/L. Note any position with no stop loss —
   that is the finding that matters most.
4. Compute total exposure as a share of equity. Call out concentration: several
   positions on correlated symbols (EURUSD and GBPUSD, XAUUSD and silver) is one
   bet, not three.
5. Call `mt5_performance` over 30 days and report win rate, profit factor and
   net profit. If there are fewer than 20 trades, say the sample is too small to
   read anything into.

Close with at most three observations, ranked by how much money they concern.
Do not offer trade ideas unless asked.
