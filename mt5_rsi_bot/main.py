"""MetaTrader 5 RSI bot.

Watches one symbol, and on each newly closed candle looks for RSI crossing back
through the oversold or overbought line. A cross back up through oversold buys,
a cross back down through overbought sells. Stops and targets go on with the
order, so a disconnection cannot leave a position unprotected.

Not a validated edge. Textbook RSI mean reversion, implemented carefully.
Paper-trade it and form your own view before it touches money.
"""

import signal
import sys
import time
from datetime import datetime, timezone

import pandas as pd

from config import Config

# Imported defensively so the pure functions below (RSI, signal detection, stop
# arithmetic) can be imported and tested on any platform. The package only
# publishes Windows wheels; initialize_mt5 gives a real explanation if it is
# missing when it actually matters.
try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None


RUNNING = True


def log(message, *, level="INFO"):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    stream = sys.stderr if level in {"ERROR", "WARN"} else sys.stdout
    print(f"{stamp} {level:<5} {message}", file=stream, flush=True)


# ---------------------------------------------------------------------------
# Indicator
# ---------------------------------------------------------------------------


def compute_rsi(closes, period):
    """Wilder's RSI: SMA seed, then recursive smoothing.

    This is what MetaTrader's own RSI indicator draws, so the numbers here match
    the chart. An unseeded EWM — what several convenience libraries use — is off
    by several points until it has warmed up.

    Returns a pandas Series aligned with `closes`, NaN until there is enough
    data.
    """

    closes = pd.Series(closes, dtype="float64").reset_index(drop=True)
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.rolling(period).mean().copy()
    avg_loss = loss.rolling(period).mean().copy()

    for i in range(period + 1, len(closes)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period

    rs = avg_gain / avg_loss
    rsi = 100 - 100 / (1 + rs)
    # avg_loss of zero means an unbroken run of gains: RSI is 100, not NaN.
    rsi[(avg_loss == 0) & (avg_gain > 0)] = 100.0
    rsi[(avg_loss == 0) & (avg_gain == 0)] = 50.0
    return rsi


def detect_signal(previous_rsi, current_rsi):
    """"BUY", "SELL" or None from two consecutive closed-bar RSI readings.

    The test is a *cross back through* the line, not merely being beyond it.
    RSI can sit under 30 for the whole of a downtrend; a plain threshold test
    buys every bar of it.
    """

    if previous_rsi is None or current_rsi is None:
        return None
    if pd.isna(previous_rsi) or pd.isna(current_rsi):
        return None

    if previous_rsi < Config.RSI_OVERSOLD <= current_rsi:
        return "BUY"
    if previous_rsi > Config.RSI_OVERBOUGHT >= current_rsi:
        return "SELL"
    return None


# ---------------------------------------------------------------------------
# Broker
# ---------------------------------------------------------------------------


def initialize_mt5():
    if mt5 is None:
        log(
            "the MetaTrader5 package is not installed. It publishes Windows "
            "wheels only — run this bot on Windows, or on Linux with the "
            "terminal under Wine.",
            level="ERROR",
        )
        sys.exit(1)

    if not mt5.initialize():
        log(f"MT5 initialization failed: {mt5.last_error()}", level="ERROR")
        sys.exit(1)

    if Config.LOGIN and Config.PASSWORD and Config.SERVER:
        if not mt5.login(Config.LOGIN, password=Config.PASSWORD, server=Config.SERVER):
            log(
                f"failed to log into account {Config.LOGIN}: {mt5.last_error()}",
                level="ERROR",
            )
            mt5.shutdown()
            sys.exit(1)
        log(f"logged into account {Config.LOGIN} on {Config.SERVER}")

    account = mt5.account_info()
    if account is None:
        log(f"could not read the account: {mt5.last_error()}", level="ERROR")
        mt5.shutdown()
        sys.exit(1)

    # A symbol the terminal has not selected returns None for everything.
    info = mt5.symbol_info(Config.SYMBOL)
    if info is None:
        log(
            f"symbol {Config.SYMBOL} is unknown to this broker. Brokers rename "
            "instruments (BTCUSD.m, BTCUSD_i); check Market Watch for the exact "
            "spelling.",
            level="ERROR",
        )
        mt5.shutdown()
        sys.exit(1)
    if not info.visible and not mt5.symbol_select(Config.SYMBOL, True):
        log(f"could not select {Config.SYMBOL} in Market Watch", level="ERROR")
        mt5.shutdown()
        sys.exit(1)

    validate_against_symbol(mt5.symbol_info(Config.SYMBOL))

    log(f"account {account.login}: balance {account.balance:.2f} {account.currency}")
    log(f"strategy: {Config.describe()}")
    if Config.DRY_RUN:
        log("DRY_RUN is on — signals are logged, no orders are sent")
    return account


def validate_against_symbol(info):
    """Check the configured lot size and stop distance against the contract.

    This is where a unit mistake gets caught. `SL_PIPS * point` on a two-digit
    symbol is a rounding error, not a stop, and the broker would either reject
    the order or fill it into an instant stop-out.
    """

    if not (info.volume_min <= Config.LOT_SIZE <= info.volume_max):
        log(
            f"LOT_SIZE {Config.LOT_SIZE} is outside {Config.SYMBOL}'s allowed "
            f"range {info.volume_min}–{info.volume_max}",
            level="ERROR",
        )
        sys.exit(2)

    steps = Config.LOT_SIZE / info.volume_step
    if abs(steps - round(steps)) > 1e-6:
        log(
            f"LOT_SIZE {Config.LOT_SIZE} is not a multiple of {Config.SYMBOL}'s "
            f"volume step {info.volume_step}",
            level="ERROR",
        )
        sys.exit(2)

    tick = mt5.symbol_info_tick(Config.SYMBOL)
    if tick is None or not tick.ask:
        log("could not read a tick to sanity-check the stop distance", level="WARN")
        return

    _, _, distance = Config.stop_levels("BUY", tick.ask, info.point, info.digits)
    distance_pct = 100 * distance / tick.ask
    spread = tick.ask - tick.bid

    if distance_pct < Config.MIN_STOP_PERCENT:
        log(
            f"REFUSING TO START: the configured stop is {distance:.{info.digits}f} "
            f"on a price of {tick.ask:.{info.digits}f} — {distance_pct:.4f}% of "
            f"price, below the {Config.MIN_STOP_PERCENT}% floor. On {Config.SYMBOL} "
            f"a point is {info.point}, so SL_PIPS is not the unit you think it is. "
            "Use SL_MODE=percent, or raise SL_PIPS to match this instrument.",
            level="ERROR",
        )
        sys.exit(2)

    if distance < spread * 3:
        log(
            f"REFUSING TO START: the stop ({distance:.{info.digits}f}) is within "
            f"three spreads ({spread:.{info.digits}f}). It would be hit on entry.",
            level="ERROR",
        )
        sys.exit(2)

    log(
        f"stop distance {distance:.{info.digits}f} "
        f"({distance_pct:.2f}% of price, spread {spread:.{info.digits}f})"
    )


TIMEFRAMES = {
    "M1": "TIMEFRAME_M1", "M5": "TIMEFRAME_M5", "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30", "H1": "TIMEFRAME_H1", "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1", "W1": "TIMEFRAME_W1", "MN1": "TIMEFRAME_MN1",
}


def get_latest_data():
    """Closed candles with RSI attached, or None.

    The final row from copy_rates_from_pos is the *forming* candle. Its RSI
    moves with every tick and can cross a threshold and cross back before the
    bar closes, so it is dropped here. Acting on closed bars only is the
    difference between a signal and a rumour.
    """

    timeframe = getattr(mt5, TIMEFRAMES[Config.TIMEFRAME])
    rates = mt5.copy_rates_from_pos(Config.SYMBOL, timeframe, 0, Config.BAR_COUNT + 1)
    if rates is None or len(rates) < Config.RSI_PERIOD + 2:
        return None

    df = pd.DataFrame(rates)
    df = df.iloc[:-1]  # drop the incomplete candle
    df["rsi"] = compute_rsi(df["close"], Config.RSI_PERIOD)
    return df


def own_positions():
    positions = mt5.positions_get(symbol=Config.SYMBOL)
    if positions is None:
        return []
    return [p for p in positions if p.magic == Config.MAGIC_NUMBER]


def open_position(action_type):
    tick = mt5.symbol_info_tick(Config.SYMBOL)
    info = mt5.symbol_info(Config.SYMBOL)
    if not tick or not info:
        log("failed to pull market tick info", level="ERROR")
        return

    if action_type == "BUY":
        price, order_type = tick.ask, mt5.ORDER_TYPE_BUY
    else:
        price, order_type = tick.bid, mt5.ORDER_TYPE_SELL

    sl, tp, distance = Config.stop_levels(action_type, price, info.point, info.digits)

    log(
        f"{action_type} {Config.LOT_SIZE} {Config.SYMBOL} @ {price:.{info.digits}f} "
        f"sl {sl:.{info.digits}f} tp {tp:.{info.digits}f} "
        f"(stop {100 * distance / price:.2f}% of price)"
    )

    if Config.DRY_RUN:
        log("DRY_RUN: no order sent")
        return

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": Config.SYMBOL,
        "volume": Config.LOT_SIZE,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": Config.DEVIATION,
        "magic": Config.MAGIC_NUMBER,
        "comment": "RSI Automated Entry",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    # order_send returns None on a transport failure. Reading .retcode off it
    # raises AttributeError, which would kill the loop.
    if result is None:
        log(f"[{action_type} FAILED] order_send returned nothing: {mt5.last_error()}",
            level="ERROR")
        return

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"[{action_type} SUCCESS] filled {result.volume} at {result.price}")
    else:
        log(
            f"[{action_type} REJECTED] retcode {result.retcode}: {result.comment}",
            level="ERROR",
        )


# ---------------------------------------------------------------------------
# Daily loss limit
# ---------------------------------------------------------------------------


class DailyLossGuard:
    """Stops new entries once the day's budget is spent. Resets at UTC midnight.

    It blocks entries rather than flattening: open positions already carry stops,
    and force-closing them at an arbitrary moment turns a managed loss into a
    realised one. If your account rules require flat, the error line below is
    your cue to close by hand.
    """

    def __init__(self, limit_percent):
        self.limit_percent = limit_percent
        self._day = None
        self._opening_equity = None
        self._tripped = False

    def check(self, equity):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._day:
            self._day = today
            self._opening_equity = equity
            self._tripped = False
            log(f"new trading day {today}, opening equity {equity:.2f}")

        if not self._opening_equity:
            return True

        change = 100 * (equity - self._opening_equity) / self._opening_equity
        if change > -self.limit_percent:
            return True

        if not self._tripped:
            self._tripped = True
            log(
                f"DAILY LOSS LIMIT HIT: equity {equity:.2f} is {abs(change):.2f}% "
                f"below today's opening {self._opening_equity:.2f} (limit "
                f"{self.limit_percent:g}%). No new entries until UTC midnight. "
                "Open positions keep their stops — close by hand if your account "
                "rules require flat.",
                level="ERROR",
            )
        return False


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------


def handle_stop(signum, _frame):
    global RUNNING
    RUNNING = False
    log(f"received {signal.Signals(signum).name}, shutting down after this cycle")


def run_bot():
    initialize_mt5()
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    guard = DailyLossGuard(Config.MAX_DAILY_LOSS_PERCENT)
    interactive = sys.stdout.isatty()
    last_bar = None

    while RUNNING:
        started = time.monotonic()
        try:
            df = get_latest_data()
            if df is None or df.empty:
                log(f"no candle data for {Config.SYMBOL}", level="WARN")
            else:
                bar_time = int(df["time"].iloc[-1])
                current_rsi = df["rsi"].iloc[-1]
                positions = own_positions()

                if interactive:
                    sys.stdout.write(
                        f"\rRSI: {current_rsi:.2f} | open: {len(positions)}   "
                    )
                    sys.stdout.flush()

                # Everything below acts once per closed bar, not once per poll.
                if bar_time != last_bar:
                    last_bar = bar_time
                    previous_rsi = df["rsi"].iloc[-2]
                    action = detect_signal(previous_rsi, current_rsi)

                    if interactive:
                        sys.stdout.write("\r")

                    log(
                        f"bar {datetime.fromtimestamp(bar_time, timezone.utc):%Y-%m-%d %H:%M} "
                        f"close {df['close'].iloc[-1]} rsi {previous_rsi:.2f} → "
                        f"{current_rsi:.2f} | {action or 'no signal'} | "
                        f"{len(positions)} open"
                    )

                    if action and len(positions) >= Config.MAX_OPEN_POSITIONS:
                        log(
                            f"{action} signal ignored: already at "
                            f"{Config.MAX_OPEN_POSITIONS} open position(s)"
                        )
                    elif action:
                        account = mt5.account_info()
                        if account is None:
                            log("could not read equity, skipping entry", level="WARN")
                        elif guard.check(account.equity):
                            log(f"[SIGNAL] {action} — RSI {previous_rsi:.2f} → "
                                f"{current_rsi:.2f}")
                            open_position(action)

        except Exception as exc:  # noqa: BLE001 — one bad cycle must not stop the bot
            log(f"cycle failed ({type(exc).__name__}): {exc}", level="ERROR")

        # Sleep in slices so SIGTERM does not wait out a whole poll interval.
        remaining = max(Config.POLL_SECONDS - (time.monotonic() - started), 0)
        while RUNNING and remaining > 0:
            nap = min(remaining, 1.0)
            time.sleep(nap)
            remaining -= nap

    if mt5 is not None:
        mt5.shutdown()
    log("stopped")


if __name__ == "__main__":
    run_bot()
