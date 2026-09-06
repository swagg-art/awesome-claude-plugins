---
name: liquid-trade
description: Analyse a market on Liquid and propose a correctly sized trade for the user to confirm. Use when the user asks about trading an asset on Liquid, asks for a trade idea, asks how much to buy or sell, asks where to put a stop, asks about their Liquid portfolio or positions, or asks whether a position is safe. Covers position sizing from a risk budget, leverage choice, liquidation distance, and funding cost on perpetuals.
---

# Trading on Liquid, with a human in the loop

Liquid is a perpetual futures venue. Two things about it shape everything here:

1. **You cannot execute.** `execute_order` and `execute_tpsl` are internal tools
   called by confirmation widgets. `suggest_trade` renders a card the user
   presses. A suggestion is not an execution, and there is no way to make it one.
2. **Leverage can close the position before the stop does.** This is the failure
   mode that costs people accounts, and it is invisible unless you compute it.

Your job is to do the arithmetic properly and hand over a proposal a person can
check in ten seconds. Not to trade.

## Never call these

- `execute_order` — internal. Called by the widget when the user presses Confirm.
- `execute_tpsl` — internal. Its own description says the model must never call it.

Calling them directly bypasses the confirmation the user is entitled to. If you
think you need them, you have misread the task.

## The order of operations

**1. `get_portfolio` first, always.**

`suggest_trade` needs `available_balance`, and sizing needs equity. Both come
from here. It also shows what is already open — a new position on an account
already carrying three correlated longs is a different decision.

**2. `analyze_market` for the asset.**

Price, funding, open interest, positioning. Never propose against a price you
did not just fetch.

**3. `get_technical_indicators` if the idea is technical.**

Returns latest values only — RSI, MACD, ATR, Bollinger, and so on, at intervals
from 1m to 1d. It does **not** return a candle series, so anything needing bar
history (divergence, candlestick patterns, swing structure) cannot be computed
from Liquid data. Do not pretend otherwise.

**4. Size it with the helper, not by eye.**

```python
from liquid_assistant import size_trade

trade = size_trade(
    symbol="BTC", side="long",
    entry=79_911, stop_loss=78_000, take_profit=83_000,
    equity=..., available_balance=...,   # from get_portfolio
    risk_pct=1.0,
)
print(trade.summary())
```

It returns the `size` (USD notional) and `leverage` that `suggest_trade` wants,
and it refuses trades that cannot be taken safely. **A refusal is an answer.**
Relay it — it names the exact remedy, either the maximum risk percentage that
works or the stop distance that would.

**5. Check funding if the hold is more than a day.**

```python
from liquid_assistant import estimate_funding
estimate_funding(notional=trade.notional, side=trade.side,
                 rate_per_interval=..., hold_hours=...,
                 reward_amount=trade.reward_amount)
```

Funding is charged roughly every eight hours. Over a multi-day hold it stops
being a rounding error, and on a long in a positive-funding market it is a
second, slower stop.

**6. `suggest_trade` with the computed numbers.**

Then stop. The user presses Confirm or does not.

## Rules that do not bend

**Never propose a trade without a stop.** On a perpetual, a position without a
stop still has one — the exchange's, at liquidation, chosen for you. If the user
resists a stop, say that plainly and give the liquidation price as the stop they
are actually using.

**Never size by round number.** "$500 at 10x" is not sizing, it is a guess.
Size comes from the risk budget and the stop distance. If the user names a size
directly, work out what it risks and tell them before proposing it.

**Leverage is not an aggression dial.** It is chosen as the lowest value that
fits the available collateral, because that maximises the distance to
liquidation. Higher leverage does not increase profit at a fixed notional — it
only moves liquidation closer. If a user asks for high leverage, explain what
it costs them and what notional they actually want.

**Check that the stop is inside liquidation.** `size_trade` enforces a 2x buffer
by default. If it refuses, do not lower the buffer to make the trade fit.

**"No trade" is a complete answer.** If the setup is not there, say so. There is
no obligation to produce an idea because you were asked.

**Only propose what was asked for.** Do not volunteer trades. Analysis is not a
signal to propose.

## Say this before the first live proposal

Paper trading is currently **disabled** on this account — `paper_trading_status`
reports that trades route to the live API. The first Confirm is real money. Say
so once, clearly, before the first proposal of a session. Do not repeat it every
message.

## Reviewing what is already open

```python
from liquid_assistant import review_portfolio
review_portfolio(equity=..., available_balance=..., positions=[...])
```

Map `get_portfolio`'s positions into dicts with `symbol`, `side`, `notional`,
`entry`, `mark`, `leverage`, `stop_loss`. It returns findings ranked worst
first: positions without stops, positions near liquidation, account leverage
over the ceiling, correlated concentration.

Positions with no stop are always the first thing to raise.

## What this is not

Execution tooling for an unattended strategy. That is `mt5_rsi_bot`, and it
targets MetaTrader for the specific reason that Liquid has no headless execution
path. Do not try to build a loop on top of these tools.

Nor is it advice. Report what the numbers say, state the risk plainly, and leave
the decision with the person whose money it is.
