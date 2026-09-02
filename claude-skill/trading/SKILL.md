---
name: trading
description: Trade and analyse a MetaTrader 5 account from the command line - place market and pending orders, attach or move stop-loss and take-profit, close positions, size trades from account risk, review a synced trade journal, and backtest rules on historical bars. Use when the user asks to buy, sell, short, close, or scale a position, check their account, balance, equity, margin, open positions or pending orders, quote a symbol, size a trade, review their trading performance, or test a strategy - and whenever MT5, MetaTrader, mt5ctl, lots, pips, or a broker symbol like EURUSD or XAUUSD comes up.
---

# MT5 trading

Everything runs through `mt5ctl` (in `scripts/`). It talks to a running
MetaTrader 5 terminal through the official Python API.

## Execution contract

**A trade request is the authorization. Send it.** When the user says "buy 0.1
EURUSD", place the order — do not reply asking whether they are sure, do not
propose it and wait, do not restate it for approval. They asked; execute, then
report the fill.

Three things are still yours to do, and none of them is a confirmation prompt:

1. **Never invent a missing parameter.** No volume given and no default in
   config? Ask for the volume — that is a missing input, not a permission
   check. Same for a ticket when several positions could match.
2. **Resolve real ambiguity before sending.** "Close EURUSD" with two EURUSD
   positions open, one long one short, is ambiguous: show them and ask which.
   "Close my EURUSD long" is not ambiguous — close it.
3. **Let validation fail loudly.** `mt5ctl` checks the volume step, the fill
   policy, and stop distances before anything reaches the broker. Report the
   error it gives you; do not retry the same order hoping for a different
   answer.

`--dry-run` prints the exact request without sending it. Use it when the user
asks what an order *would* look like, never as a substitute for executing one
they asked for.

## The commands

```bash
mt5ctl account                    # balance, equity, margin, DEMO or LIVE
mt5ctl positions [SYMBOL]         # open positions with floating P&L
mt5ctl orders                     # working pending orders
mt5ctl quote EURUSD XAUUSD        # bid/ask/spread, lot min/max/step
mt5ctl symbols GOLD               # what this broker actually calls it
mt5ctl bars EURUSD --tf H1 --show 30

mt5ctl buy  EURUSD 0.10 --sl 1.0820 --tp 1.0900
mt5ctl sell XAUUSD 0.05 --sl 2325.00
mt5ctl pending EURUSD buy limit 0.10 1.0800 --sl 1.0770
mt5ctl modify 880011 --sl 1.0850          # move the stop on an open position
mt5ctl close 880011 [--volume 0.05]       # full or partial
mt5ctl close-all [--symbol EURUSD]
mt5ctl cancel 880042                      # delete a pending order

mt5ctl size EURUSD --risk 1 --entry 1.0850 --stop 1.0820
mt5ctl heat                               # open risk across the book

mt5ctl journal sync --days 90
mt5ctl journal stats --by-symbol
mt5ctl journal list
mt5ctl journal note --id 880011 --text "..." --setup breakout

mt5ctl backtest EURUSD --tf H1 --bars 3000 --strategy ma_cross \
  --param fast=8 --param slow=21 --spread 12
```

Add `--json` to any command when you need to compute on the result rather than
show it. Everything else prints tables meant to be pasted straight through.

## Workflows

Chain these; do not stop halfway to check in.

**Entry with protection.** MT5 accepts SL/TP on the entry request, so one call
does it — prefer this over entering naked and attaching stops afterwards:

```bash
mt5ctl buy EURUSD 0.10 --sl 1.0820 --tp 1.0900
```

If the user gives a stop but no target, send the stop alone. If they give
neither, send the order — then say plainly that it has no stop.

**Risk-sized entry.** When they name a risk percentage instead of a lot size,
size it, then send it:

```bash
mt5ctl size EURUSD --risk 1 --entry 1.0850 --stop 1.0820   # → 0.33 lots
mt5ctl buy EURUSD 0.33 --sl 1.0820
```

**Break-even move.** Read the position, then move the stop to entry:

```bash
mt5ctl positions EURUSD
mt5ctl modify 880011 --sl 1.08350
```

**Scale out.** Partial close, then trail the rest:

```bash
mt5ctl close 880011 --volume 0.05
mt5ctl modify 880011 --sl 1.08500
```

**After the session.** Sync and review — the journal keeps your notes and takes
the broker's numbers as truth:

```bash
mt5ctl journal sync --days 30 && mt5ctl journal stats --by-symbol
```

## Presenting results

The CLI already renders tables; pass them through rather than rewriting them
into prose or markdown tables. After an order, state the four things that
matter: **side, volume, symbol, fill price**, plus the ticket. After a close,
state the realized P&L.

Report what happened, not what you hope happened. If a stop was rejected for
being too close, say so and give the broker's minimum distance — do not quietly
drop the stop and place a naked order.

## MT5 knowledge you need

- **Symbols are broker-specific.** `EURUSD` may really be `EURUSD.raw`,
  `EURUSDm`, or `EURUSD_i`; gold is `XAUUSD` on most brokers and `GOLD` on
  some. `mt5ctl` resolves unique prefixes automatically and lists candidates
  when a name is ambiguous — run `mt5ctl symbols <partial>` rather than
  guessing.
- **Volume is in lots**, constrained by `volume_min` / `volume_max` /
  `volume_step` per symbol. 0.1234 lots is not a thing; it becomes 0.12.
- **Filling modes matter.** A broker that only accepts FOK will reject an IOC
  order with retcode 10030. The client reads the symbol's mask and picks a
  policy that works.
- **Stops have a minimum distance** (`trade_stops_level`). Inside it, the
  broker returns 10016.
- **Timeframes** are `M1 M5 M15 M30 H1 H4 D1 W1 MN1`.
- **Retcode 10009 is success**; 10008 means a pending order was placed.
  Anything else is a real failure with a real reason — `reference/mt5-domain.md`
  has the full table.

Deeper detail lives in `reference/`: `mt5-domain.md` for order types, retcodes
and lot maths, `workflows.md` for longer recipes, `setup.md` for installation
and the Windows-only caveat, `analysis.md` for the journal, sizing and
backtester.

## Bounds

`~/.config/mt5-trading/config.json` carries `max_volume`, `allowed_symbols` and
`dry_run`. These are the user's own limits — when an order trips one, report it
and stop; widening the config is their decision to make, not yours.

`mt5ctl account` shows **DEMO** or **LIVE**. Mention which one when the user
opens a session or asks what account they are on. Nothing here is a
recommendation to take a trade — the user decides what to trade, this executes
and measures it.
