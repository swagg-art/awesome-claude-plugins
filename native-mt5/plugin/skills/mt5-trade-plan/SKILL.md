---
name: mt5-trade-plan
description: Turn a trade idea into a sized, stop-defined plan against a live MetaTrader 5 account. Use when the user describes wanting to buy or sell an instrument, asks "how many lots", asks to size a position, asks where to put a stop, or asks to place, preview or close an MT5 order. Also use when checking what a trade would risk before committing to it.
---

# Building an MT5 trade plan

A trade idea is not a trade. This skill turns "I want to buy gold" into a plan
with a size, a stop, and a number for what it costs when it goes wrong.

## The order of operations

Never skip to `mt5_place_order`. The sequence is always:

1. **`mt5_status`** — establish which account and which mode. In `readonly` you
   can plan but not execute; say that up front rather than at the end.
2. **`mt5_symbol_info`** — get the contract spec. Brokers rename instruments
   (`XAUUSD.m`, `EURUSD_i`), so use `mt5_list_symbols` with a search term rather
   than assuming a name exists.
3. **`mt5_quote`** and **`mt5_candles`** — current price and enough history to
   place a stop somewhere defensible.
4. **`mt5_size_position`** — never compute lot size yourself. The tool knows the
   tick value, the volume step and the server's risk ceiling, and it rounds
   down rather than up.
5. **`mt5_preview_order`** — always, even in paper mode. It reports the spread
   cost, the money at risk, and whether the guards will accept the order.
6. **`mt5_place_order`** — only after the human has seen the preview.

## Where the stop goes

Place the stop where the idea is wrong, then size to it. Sizing first and
squeezing the stop to fit is how accounts die.

- Use structure from `mt5_candles`: below the recent swing low for a long, above
  the swing high for a short.
- Leave room for the spread. A stop inside the spread is hit on entry.
- An order without a stop has unbounded downside. If the user insists on one,
  state the exposure in account currency and let them confirm.

## Reading the sizing result

`mt5_size_position` returns `volume`, `loss_at_stop` and `reward_risk_ratio`.

- `capped_by` set means the server's caps shrank the position below the
  requested risk. Say which cap bit — the user may want to change the config,
  not the trade.
- A `reward_risk_ratio` under 1 means the target pays less than the stop costs.
  Say so; it may still be a fine trade at a high enough win rate, but the user
  should decide that knowingly.
- A `RiskError` about the minimum lot means the stop is too wide for the
  account. The fix is a smaller stop or a smaller contract, never a bigger risk
  percentage.

## Executing

In `live` mode `mt5_place_order` requires the `confirmation_token` from
`mt5_preview_order` for exactly those arguments. This is deliberate: change the
volume and the token stops working. Show the preview to the human, get an
explicit yes, then pass the token through unchanged.

Never place an order the user did not ask for. Never widen a stop to avoid a
loss. Never average into a losing position on your own initiative.

## What this is not

This is execution tooling, not advice. Report what the numbers say, note the
risk plainly, and leave the decision with the person whose money it is.
