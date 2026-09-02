# Sizing, journal and backtesting

The analysis side. None of it places orders, and all of it is pure Python — the
maths is testable and the numbers are checkable by hand.

## Position sizing

```bash
mt5ctl size EURUSD --risk 1 --entry 1.0850 --stop 1.0820
```

```
value_per_lot = trade_tick_value / trade_tick_size
lots          = (balance × risk% / 100) / (|entry − stop| × value_per_lot)
```

Then rounded **down** to `volume_step` and bounded by the symbol's min/max and
your `max_volume`. Rounding down matters: rounding 0.3333 up to 0.34 quietly
puts you over the risk budget you just specified.

Three ways it refuses, all of them deliberate:

- **Stop too wide for the account.** The maths asks for less than the minimum
  lot. Widen the risk, tighten the stop, or skip the trade — it will not
  silently hand you the minimum lot and a bigger loss than you asked for.
- **`entry == stop`.** No risk to size against.
- **`risk_pct` outside 0–100.** A typo, not an instruction.

`--balance` overrides the account figure for what-ifs.

## Portfolio heat

```bash
mt5ctl heat
```

Sums `|entry − stop| × volume × value_per_lot` across open positions and
reports it as a percentage of equity. Positions **without** a stop cannot be
summed — their loss is unbounded — so they are reported as a separate count and
symbol list rather than being treated as zero risk.

## Journal

Stored as JSONL at `~/.local/share/mt5-trading/journal.jsonl`
(`MT5_JOURNAL` overrides). One line per closed trade, append-only in spirit and
diffable.

```bash
mt5ctl journal sync --days 90       # fold MT5 deal history into round trips
mt5ctl journal list                 # recent trades
mt5ctl journal stats --by-symbol    # the numbers
mt5ctl journal note --id 880011 --text "chased it" --setup breakout --tags fx london
```

**Sync is idempotent.** Broker facts (prices, volumes, profit, times) are
overwritten from MT5 every time; your own fields — `note`, `setup`, `tags`,
`planned_r` — survive. So re-syncing a wider window never costs you notes.

Partial closes are folded correctly: several exit deals sharing a
`position_id` sum into one trade with `partial_exits` recording how many.
A position still open is skipped rather than half-counted.

### What the stats mean

| Metric | Definition |
|---|---|
| Win rate | wins ÷ closed trades |
| Net P&L | sum of net (profit + commission + swap) |
| Expectancy | net ÷ trades — what an average trade returns |
| Profit factor | gross wins ÷ gross losses; >1 is profitable, 1.5+ is solid |
| Payoff ratio | average win ÷ average loss |
| Max drawdown | largest peak-to-trough decline of the cumulative P&L curve |
| Average R | mean R multiple, when trades carry an `r` field |

All of them run on **net**, after commission and swap. Gross-profit stats
flatter a strategy that trades often, which is exactly the strategy costs kill.

Expectancy and profit factor are the pair worth reading together: a 30% win
rate with a 3:1 payoff beats a 70% win rate with a 1:3 payoff, and only the
combination tells you which you have.

## Backtester

```bash
mt5ctl backtest EURUSD --tf H1 --bars 5000 --strategy ma_cross \
  --param fast=8 --param slow=21 --spread 12 --stop 300 --target 600 --long-only
```

Built-in strategies:

| Name | Parameters | Rule |
|---|---|---|
| `ma_cross` | `fast`, `slow` | Long above, short below, reverse on the cross |
| `rsi_reversion` | `period`, `low`, `high` | Buy oversold, sell overbought, flatten through 50 |
| `breakout` | `lookback` | Break of the N-bar high or low |

### What it does and does not model

Honest about its limits, because a backtest that flatters itself is worse than
none:

- **Signals fill at the next bar's open**, never on the signal bar. Filling on
  the bar that produced the signal is lookahead and manufactures edges.
- **One position at a time.** No pyramiding, no hedging.
- Stops and targets are checked **intrabar**, against the bar's high and low.
  When both could have been hit in one bar, the stop is taken first — the
  pessimistic assumption.
- Spread is a **fixed** cost in points, applied to both sides. Real spread
  widens exactly when your strategy wants to trade.
- **No swap, no commission, no slippage, no partial fills, no margin calls.**
- Results are in **points**, not currency — multiply by value-per-lot for
  money.

Treat the output as evidence that a rule was or was not profitable on that
history, not as a forecast. `--spread` is the single most important knob: a
strategy that only works at zero spread does not work.

## Extending it

A strategy is any callable `signal(index, bars, ctx)` returning `"buy"`,
`"sell"`, `"close"` or `None`, optionally with a `.build(bars)` that
precomputes indicators once. `sma`, `rsi` and `atr` are already there. Add a
factory to `STRATEGIES` in `scripts/backtest.py` and it appears in `--strategy`
automatically.
