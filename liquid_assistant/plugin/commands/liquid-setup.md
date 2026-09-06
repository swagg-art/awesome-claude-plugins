---
description: Analyse one Liquid market and, if there is a case for it, propose a sized trade.
argument-hint: [symbol] [optional risk %]
---

Work up `$1` as a trade candidate. Risk defaults to 1% of equity unless `$2`
says otherwise.

1. `get_portfolio` — equity, available balance, and what is already open. If the
   account already holds this asset, say so and stop unless the user wants to add
   deliberately.
2. `analyze_market` for `$1` — price, funding, open interest, positioning.
3. `get_technical_indicators` for `$1` if the case is technical. Remember these
   are latest values only; there is no candle series behind them.
4. State the case in two or three sentences, or say there isn't one. **"No setup
   here" is a valid and often correct answer** — do not manufacture a trade.
5. If there is a case: pick the stop from where the idea would be wrong, then
   size it with `liquid_assistant.size_trade`. Never the other way round.
6. If the hold is likely to exceed a day, run `estimate_funding` and include the
   cost.
7. Show `trade.summary()` to the user, then call `suggest_trade` with the
   computed `size` and `leverage`.

If `size_trade` refuses, relay the refusal and the remedy it names. Do not
lower the liquidation buffer or raise the risk to make a trade fit.

Say once, before the first proposal in a session, that paper trading is disabled
and Confirm means real money.
