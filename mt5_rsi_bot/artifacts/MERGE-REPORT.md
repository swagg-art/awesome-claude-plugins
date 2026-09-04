# mt5_rsi_bot — merge report

**Date:** 2026-09-04
**Inputs:** the six files as supplied, merged with the earlier implementation.

Your structure, function names, environment variable names and service name
(`rsibot`) were kept. Changes below are limited to things that were measured to
be broken, or that would cost money.

## Changed after measuring

### `pandas-ta` removed

Two findings, both reproduced rather than assumed:

1. **It will not install on Python 3.11.** `pandas-ta>=0.3.14b0` now resolves to
   0.4.71b0, which requires Python 3.12+. On 3.11 the resolver fails outright:
   *"all versions of pandas-ta depend on Python>=3.12"*.
2. **Its RSI is not Wilder's.** It uses an unseeded EWM; MetaTrader's own RSI
   indicator uses SMA-seeded Wilder smoothing. On Wilder's canonical 20-bar
   series pandas-ta returns 50.66 where the published value is 70.5, and it
   emits non-NaN values from index 1 — impossible for a 14-period indicator.

   In fairness, at the 100 bars this bot fetches the two converge: across 300
   random 100-bar series the worst difference was **0.154 RSI points, with zero
   disagreements about a 30/70 crossing**. So this was not going to ruin the
   strategy. But it differs by 7+ points during warm-up, and it is a beta
   dependency carrying a Python floor for one 15-line function.

RSI now lives in `main.py`, returns 70.46 on Wilder's series, and is NaN until
warmed up.

### Stop distances: the one that would have cost money

`sl = price - (SL_PIPS * point)` with `SL_PIPS=200` on `MT5_SYMBOL=BTCUSD`:

| Symbol | point | `SL_PIPS=200` gives | as % of price |
| --- | --- | --- | --- |
| BTCUSD @ $64,000 | 0.01 | **a $2.00 stop** | 0.0031% |
| EURUSD @ 1.08500 | 0.00001 | a 20-pip stop | 0.18% |

The $2 stop is hit by the spread on entry, every time. The variable is also
named `SL_PIPS` but used as *points* — on a 5-digit pair those differ by 10x.

Rather than silently redefining your knob, there is now `SL_MODE`:

- `percent` (new default) — stop as a share of entry price, so it means the same
  thing on EURUSD at 1.08 and BTCUSD at 64000.
- `points` — your original arithmetic, unchanged, for when you have checked
  `symbol.point` yourself.

And a startup check that **refuses to start** if the resulting stop is under
`MIN_STOP_PERCENT` of price or inside three spreads. Verified: the original
BTCUSD settings are now rejected with an explanation.

## Bugs fixed

| Issue | Consequence |
| --- | --- |
| Signal read from the **forming** candle (`iloc[-1]` of `copy_rates_from_pos(…, 0, 100)`) | RSI repaints tick by tick; a cross can appear and vanish before the bar closes. Now drops the incomplete bar and acts once per closed bar. |
| `result.retcode` without a None check | `order_send` returns None on transport failure → `AttributeError` → process dies. |
| No `try`/`except` in the loop | Any transient broker or network error killed the bot; systemd then restarted it every 10s forever. |
| `StartLimitIntervalSec`/`StartLimitBurst` absent | Nothing stopped that restart loop. Now in `[Unit]` — under `[Service]` systemd silently ignores them, confirmed with `systemd-analyze verify`. |
| `USER="$(whoami)"` in `deploy_service.sh` | Run the script under `sudo` and the service runs **as root** holding broker credentials. Now `${SUDO_USER:-$(whoami)}`. |
| `run.sh` installed dependencies only when `venv/` was absent | An edited `requirements.txt` was never picked up. Now stamped and compared. |
| `run.sh` copied `.env` then immediately launched | The bot ran against `MT5_PASSWORD=YourPasswordHere`. Now it stops and tells you to edit it. |
| `int(os.getenv("MT5_LOGIN", 0))` | `ValueError` crash if the var is present but blank. |
| `load_dotenv()` searched from cwd | Running `python /path/to/main.py` from elsewhere silently loaded no `.env`. Now an absolute path. |
| No `symbol_select` | A symbol not in Market Watch returns None for everything, with a confusing error. |
| No SIGTERM handling | `systemctl stop` killed the bot mid-order. Now finishes the cycle and calls `mt5.shutdown()`. |
| `\r` status line into journald | Fills the journal with carriage returns. Now only when stdout is a TTY. |

## Added

- **Daily loss limit** (`MAX_DAILY_LOSS_PERCENT`, default 2%). Once equity is
  that far below the day's opening, no new entries until UTC midnight. It blocks
  entries rather than flattening: open positions already carry stops, and
  force-closing turns a managed loss into a realised one.
- **`DRY_RUN`** — logs signals and intended orders without sending any.
- **Lot size validated** against the symbol's `volume_min`/`max`/`step`.
- **Partial-credential check** — setting login without server silently leaves
  you on whatever account the terminal already had open.
- **Confirmation prompts** before live trading and before enabling the service.
- **`.gitignore`** — `run.sh` creates `.env`, so without it the first run
  commits a broker password.

## Verification

| Check | Result |
| --- | --- |
| RSI vs Wilder's published series | 70.46 (published ~70.5) |
| RSI NaN before warm-up | yes |
| Signal detection, 6 cases incl. NaN and false crosses | all correct |
| Startup guard vs original BTCUSD settings | refused, exit 2 |
| Lot size below minimum / off step | refused |
| Config validation, 6 cases | all caught |
| Daily loss guard | trips at the limit, stays tripped, logs once |
| `pip install -r requirements.txt` on Python 3.11 | clean (pandas-ta would have failed) |
| `systemd-analyze verify` | clean |
| `ruff check` | clean |

## Not addressed

The strategy still has **no backtest**. Nothing here says RSI mean reversion on
BTCUSD M15 makes money — only that the bot now does what it says, refuses
configurations that would lose money to mechanics rather than to the market, and
does not crash. Run it with `DRY_RUN=true` against your broker's real data
before letting it trade.

Fixed `LOT_SIZE` also means risk per trade is unquantified: 0.01 BTC lots with a
1% stop is a different exposure than the same lots on EURUSD. Risk-based sizing
exists in `native-mt5/src/native_mt5/risk.py` if you want it wired in.
