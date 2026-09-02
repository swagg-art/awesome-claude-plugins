# Workflows

Recipes that chain several calls. Run them through; do not stop between steps
to ask for approval of a step the user already asked for.

## Enter with a stop and target

One request — MT5 accepts stops on the entry:

```bash
mt5ctl buy EURUSD 0.10 --sl 1.0820 --tp 1.0900
```

Why not enter first and attach stops after: between the two calls the position
is unprotected, and a rejected `modify` leaves it that way.

## Size from risk, then enter

```bash
mt5ctl size EURUSD --risk 1 --entry 1.0850 --stop 1.0820
# → Lots 0.33, loss if stopped 99.00 USD
mt5ctl buy EURUSD 0.33 --sl 1.0820 --tp 1.0940
```

`size` rounds **down** to the lot step, so realized risk lands at or under the
budget, never over it.

## Move to break-even

```bash
mt5ctl positions EURUSD          # read the entry price and ticket
mt5ctl modify 880011 --sl 1.08350
```

If the market has not moved far enough, the broker rejects it with 10016 —
report the minimum distance rather than nudging the stop to something the user
did not ask for.

## Scale out and trail

```bash
mt5ctl close 880011 --volume 0.05     # take half off
mt5ctl modify 880011 --sl 1.08500     # trail the remainder
```

The ticket survives a partial close, so the same ticket is used for both.

## Bracket a breakout with pending orders

```bash
mt5ctl pending EURUSD buy  stop 0.10 1.0900 --sl 1.0870
mt5ctl pending EURUSD sell stop 0.10 1.0800 --sl 1.0830
```

Nothing cancels the other side automatically — MT5 has no OCO. When one fills,
cancel the other:

```bash
mt5ctl orders
mt5ctl cancel 880042
```

## Flatten everything

```bash
mt5ctl close-all                 # every position
mt5ctl close-all --symbol XAUUSD # one symbol
```

Positions close one at a time and the output lists each result, so a partial
failure is visible rather than silent.

## Check the book before adding risk

```bash
mt5ctl heat
```

Shows open risk as a percentage of equity and — the number people forget —
**how many positions have no stop at all**. Unprotected positions are unbounded
risk, so they are counted separately rather than folded into the percentage.

## End-of-session review

```bash
mt5ctl journal sync --days 30
mt5ctl journal stats --by-symbol
mt5ctl journal note --id 880011 --text "chased the entry" --setup breakout
```

`sync` is idempotent: broker facts overwrite, your notes and tags survive.

## Test a rule before trading it

```bash
mt5ctl backtest EURUSD --tf H1 --bars 5000 --strategy ma_cross \
  --param fast=8 --param slow=21 --spread 12 --stop 300 --target 600
```

Signals are read on a bar's close and filled at the **next** bar's open. A
backtest that fills on the signal bar invents an edge that does not exist.
