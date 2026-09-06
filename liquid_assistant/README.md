# Liquid Assistant

A human-in-the-loop trading assistant for Liquid perpetuals.

It does the arithmetic that Liquid's own tools do not: turning "risk 1% of my
account" into the USD notional and leverage `suggest_trade` wants, and catching
the case where the leverage required would liquidate the position before the
stop is ever reached.

It proposes. It never executes — [by design, and not by choice](#why-it-cannot-execute).

## Why this exists

Liquid's connector takes a `size` in USD notional and a `leverage`. People think
in risk budgets. The conversion between them is where perpetual accounts die,
because two constraints pull against each other:

- **The stop defines the loss.** Notional = risk ÷ stop distance. A tighter stop
  means a *larger* position, not a smaller one.
- **Leverage defines the liquidation point.** At 40x the exchange closes you
  after roughly a 2% move — so a 3% stop on 40x is a stop that will never be
  reached.

Get those backwards and the venue closes the trade before the idea has been
proven wrong. `size_trade` solves both together, and refuses when no answer
exists rather than producing one that looks plausible.

## What it does

```python
from liquid_assistant import size_trade

trade = size_trade(
    symbol="BTC", side="long",
    entry=79_911, stop_loss=78_000, take_profit=83_000,
    equity=10_000, available_balance=5_000,   # from get_portfolio
    risk_pct=1.0,
)
print(trade.summary())
```

```
LONG BTC @ 79,911.00
  size        $4,181.63 notional at 1x ($4,181.63 collateral)
  stop        78,000.00  (2.39% away, risks $100.00 = 1.00% of equity)
  target      83,000.00  (makes $161.64, 1.62R)
  liquidation 399.56  (99.50% away — 41.6x the stop distance)
```

The notional falls out of the stop: $100 of risk over a 2.39% stop is $4,181 of
exposure. With $5,000 available it needs no leverage at all, so it takes none —
and liquidation ends up effectively irrelevant.

Run the same trade on a $800 balance and leverage appears only because it must:

```
LONG BTC @ 79,911.00
  size        $4,181.63 notional at 5.3x ($788.99 collateral)
  stop        78,000.00  (2.39% away, risks $100.00 = 1.00% of equity)
  target      83,000.00  (makes $161.64, 1.62R)
  liquidation 65,233.01  (18.37% away — 7.7x the stop distance)
```

Same position, same risk, same stop. Only the collateral and the liquidation
distance changed. Leverage is chosen as the **lowest** value that fits the
available balance, because that maximises the distance to liquidation. It is not
an aggression dial, and turning it up would not have made this trade bigger.

### When there is no safe answer

```
REFUSED: no safe leverage exists for this trade. Fitting $1,333.33 of exposure
into $300.00 needs at least 4.4x, but a 15.00% stop allows at most 3.3x if
liquidation is to stay 2x beyond the stop. [...] No stop width fixes this:
keeping liquidation 2x beyond the stop needs at least 2x the risk budget in
collateral ($400.00) and only $300.00 is available. Risk at most 1.48%, or fund
the account.
```

Every refusal names the exact remedy — the maximum risk that works, or the stop
distance that would. Both are tested to actually produce a sizeable trade.

### Funding

```python
from liquid_assistant import estimate_funding
estimate_funding(notional=10_000, side="long",
                 rate_per_interval=0.0001, hold_hours=27 * 24,
                 reward_amount=200)
# 81 intervals, $81.00 — "funding eats $81.00, 40% of the target — material"
```

A CFD charges swap overnight; a perpetual charges funding every eight hours or
so. Over a multi-day hold it is a second, slower stop.

### Portfolio review

```python
from liquid_assistant import review_portfolio
review_portfolio(equity=..., available_balance=..., positions=[...])
```

Findings ranked worst first: positions with no stop, positions near liquidation,
account leverage over the ceiling, correlated concentration. Positions without
stops always come first — on a perpetual they have a stop anyway, the exchange's.

## The plugin

`plugin/` is a Claude Code plugin: the `liquid-trade` skill teaching the order of
operations, plus `/liquid-review` (read-only account review) and `/liquid-setup`
(analyse one market and propose).

## Why it cannot execute

Not a design choice on our part. Liquid's connector reserves execution for the
user:

| Tool | Its own description |
| --- | --- |
| `execute_order` | *"INTERNAL: Called by confirmation widgets when the user presses Confirm. Do not call directly."* |
| `suggest_trade` | *"The user must press Confirm to execute — a suggestion is NOT an execution."* |
| `execute_tpsl` | *"SYSTEM INTERNAL — the model must NEVER call this tool directly."* |

That makes an unattended bot impossible on Liquid, which is why `mt5_rsi_bot`
targets MetaTrader instead. See `../mt5_rsi_bot/artifacts/LIQUID-ASSESSMENT.md`
for the full comparison.

## Development

```bash
PYTHONPATH=src python -m unittest discover -s tests   # 44 tests, no dependencies
pytest                                                 # same suite
```

Pure standard library. Every expected value in the tests is computed by hand.

## Limits

- **Liquidation prices are approximate.** Liquid does not publish its
  maintenance-margin schedule through the connector, so a conservative 0.5% is
  assumed and fees and funding are ignored — all of which bring liquidation
  *closer*. Treat the number as a ceiling on how far price can move, never an
  exact level.
- **Funding rates must be supplied.** `analyze_market` reports the current rate;
  it is not predicted here, and it floats.
- **No candle series.** Liquid returns latest indicator values only, so anything
  needing bar history — divergence, candlestick patterns, swing structure —
  cannot be computed from Liquid data.
- **Paper trading is disabled** on the account this was built against. Confirm
  means real money.

## Licence

MIT.
