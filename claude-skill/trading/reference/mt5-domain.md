# MT5 domain reference

## Order types

| Constant | Value | What it does |
|---|---|---|
| `ORDER_TYPE_BUY` | 0 | Market buy — fills at the **ask** |
| `ORDER_TYPE_SELL` | 1 | Market sell — fills at the **bid** |
| `ORDER_TYPE_BUY_LIMIT` | 2 | Buy **below** the current price |
| `ORDER_TYPE_SELL_LIMIT` | 3 | Sell **above** the current price |
| `ORDER_TYPE_BUY_STOP` | 4 | Buy **above** the current price (breakout) |
| `ORDER_TYPE_SELL_STOP` | 5 | Sell **below** the current price (breakdown) |

Getting the side of the market wrong is the most common pending-order mistake:
a buy limit placed above the market is rejected, because a limit means "I want
a better price than now".

## Trade actions

| Constant | Value | Used for |
|---|---|---|
| `TRADE_ACTION_DEAL` | 1 | Market orders, and closing a position |
| `TRADE_ACTION_PENDING` | 5 | Placing a limit/stop order |
| `TRADE_ACTION_SLTP` | 6 | Changing SL/TP on an **open position** |
| `TRADE_ACTION_MODIFY` | 7 | Changing a **pending order's** price or stops |
| `TRADE_ACTION_REMOVE` | 8 | Deleting a pending order |

Closing a position is not its own action: it is a `DEAL` in the opposite
direction carrying the original `position` ticket. Without that ticket a
"closing" order opens a second, hedged position instead.

## Filling modes

| Policy | Meaning |
|---|---|
| `ORDER_FILLING_FOK` (0) | Fill the whole volume or cancel |
| `ORDER_FILLING_IOC` (1) | Fill what is available, cancel the rest |
| `ORDER_FILLING_RETURN` (2) | Fill what is available, leave the remainder working |

`symbol_info.filling_mode` is a **bitmask** of what the broker allows —
`SYMBOL_FILLING_FOK = 1`, `SYMBOL_FILLING_IOC = 2`, so a value of 3 means both.
Sending a policy outside the mask returns retcode **10030**, which is the usual
cause of "my order works on one broker and not another".

## Timeframes

`M1` 1 · `M5` 5 · `M15` 15 · `M30` 30 · `H1` 16385 · `H4` 16388 · `D1` 16408 ·
`W1` 32769 · `MN1` 49153.

The values are not minutes past H1 — they are flag constants, which is why
`H1` is 16385 rather than 60. Use the names.

## Symbol formats

Brokers rename and suffix everything:

| You mean | It may be called |
|---|---|
| EURUSD | `EURUSD`, `EURUSD.raw`, `EURUSDm`, `EURUSD_i`, `EURUSD.pro` |
| Gold | `XAUUSD`, `GOLD`, `XAUUSD.s` |
| US 30 | `US30`, `DJ30`, `WS30`, `US30.cash` |
| Nasdaq | `NAS100`, `USTEC`, `NDX100` |

A symbol also has to be **visible in Market Watch** before it can be traded;
`symbol_select(name, True)` adds it. `mt5ctl` does this automatically.

## Volume

Lots, bounded per symbol by `volume_min`, `volume_max` and `volume_step`.
Typical forex: min 0.01, step 0.01. Round to the step *before* sending —
otherwise retcode 10014.

Value of one point of movement:

```
value_per_lot = trade_tick_value / trade_tick_size
loss_at_stop  = lots × |entry − stop| × value_per_lot
```

For a 5-digit EURUSD with `tick_value` 1.0 and `tick_size` 0.00001, one lot is
100,000 units of account currency per unit of price — so a 30-pip stop
(0.0030) on 0.33 lots risks 0.33 × 0.0030 × 100000 = **99.00**.

## Retcodes

| Code | Meaning | What to do |
|---|---|---|
| 10004 | Requote | Re-quote and resend (the client retries twice) |
| 10006 | Rejected by the dealer | Do not hammer it; report it |
| 10008 | Pending order placed | Success for a pending order |
| 10009 | Done | Success |
| 10010 | Done partially | Check the filled volume before assuming the size |
| 10013 | Invalid request | A malformed field — usually a missing `position` on a close |
| 10014 | Invalid volume | Round to `volume_step`, respect min/max |
| 10015 | Invalid price | Price is stale or wrong-sided for the order type |
| 10016 | Invalid stops | SL/TP too close, or on the wrong side of entry |
| 10017 | Trade disabled | Account is read-only |
| 10018 | Market closed | Wait for the session; check the symbol's trading hours |
| 10019 | No money | Reduce volume or free margin |
| 10020 | Prices changed | Resend with a fresh quote |
| 10026 | Autotrading disabled by the server | Broker-side; nothing local fixes it |
| 10027 | Autotrading disabled in the terminal | Press the **Algo Trading** button |
| 10030 | Unsupported filling mode | Use a policy inside `filling_mode` |
| 10031 | No connection | Terminal lost the trade server |
| 10034 | Not enough free margin | Reduce volume |

## Deals, orders, positions

Three different objects, and confusing them makes the journal wrong:

- An **order** is an instruction. It may never fill.
- A **deal** is an execution. Entry deals have `entry == 0`, exits `entry == 1`.
- A **position** is the net result, identified by `position_id`, which every
  related deal carries.

A round-trip trade is therefore one entry deal plus one or more exit deals
sharing a `position_id` — partial closes produce several exits, so profit and
volume must be **summed**, not read off the last deal.

## Magic numbers

`magic` tags an order as yours. Filtering positions by magic separates what
this tooling opened from what you clicked manually in the terminal. The default
is `777001`; change it in the config if it collides with an EA you run.
