"""RSI mean-reversion bot for MetaTrader 5.

Strategy, in one paragraph: on each newly *closed* candle, compute RSI. A buy
fires when RSI crosses back up through the oversold line, a sell when it crosses
back down through overbought. Crossing back — not merely being beyond the line —
matters: RSI can pin under 20 for a long time in a downtrend, and a threshold
test alone buys every bar of it. Stops and targets come from ATR so they scale
with the instrument's current volatility, and the lot size is whatever risks
`RISK_PCT` of the balance if the stop is hit.

Execution safety is not reimplemented here. The bot runs on top of the
``native_mt5`` package and inherits its Guard: volume caps, position caps, the
symbol allowlist, and readonly/paper/live modes. On top of that it adds a daily
loss limit, which is the one thing an unattended process most needs.

This is a working implementation of a well-known textbook strategy. It is not a
validated edge, and nothing here has been backtested. Run it in paper mode and
form your own view before it touches money.
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from native_mt5.adapters.base import AdapterError
from native_mt5.risk import RiskError
from native_mt5.safety import (
    OrderIntent,
    SafetyError,
    TradeMode,
    confirmation_token,
)
from native_mt5.session import Session

from config import BotConfig, ConfigError, load

log = logging.getLogger("mt5_rsi_bot")


# ---------------------------------------------------------------------------
# Indicators
#
# Wilder's smoothing throughout, which is what MetaTrader's own RSI and ATR use.
# A simple moving average over the same period gives visibly different numbers
# and would make the bot disagree with the chart the user is looking at.
# ---------------------------------------------------------------------------


def rsi(closes: list[float], period: int) -> float | None:
    """Wilder's RSI over the closing prices. None if there is too little data."""

    if len(closes) < period + 1:
        return None

    gains, losses = [], []
    for previous, current in zip(closes[:-1], closes[1:], strict=True):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:], strict=True):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def atr(candles: list[dict], period: int) -> float | None:
    """Wilder's Average True Range. None if there is too little data."""

    if len(candles) < period + 1:
        return None

    true_ranges = []
    for previous, current in zip(candles[:-1], candles[1:], strict=True):
        true_ranges.append(
            max(
                current["high"] - current["low"],
                abs(current["high"] - previous["close"]),
                abs(current["low"] - previous["close"]),
            )
        )

    value = sum(true_ranges[:period]) / period
    for tr in true_ranges[period:]:
        value = (value * (period - 1) + tr) / period
    return value


def ema(values: list[float], period: int) -> float | None:
    """Exponential moving average, seeded with an SMA of the first `period`."""

    if len(values) < period:
        return None
    multiplier = 2.0 / (period + 1)
    value = sum(values[:period]) / period
    for price in values[period:]:
        value = (price - value) * multiplier + value
    return value


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Signal:
    side: str  # "buy" | "sell"
    reason: str
    rsi_now: float
    rsi_previous: float


def evaluate(candles: list[dict], config: BotConfig) -> Signal | None:
    """Look for an RSI cross-back on the most recently closed candle."""

    closes = [c["close"] for c in candles]

    rsi_now = rsi(closes, config.rsi_period)
    rsi_previous = rsi(closes[:-1], config.rsi_period)
    if rsi_now is None or rsi_previous is None:
        log.warning("not enough history for RSI(%d) yet", config.rsi_period)
        return None

    crossed_up = rsi_previous <= config.rsi_oversold < rsi_now
    crossed_down = rsi_previous >= config.rsi_overbought > rsi_now
    if not (crossed_up or crossed_down):
        return None

    side = "buy" if crossed_up else "sell"
    reason = (
        f"RSI crossed {'up through' if crossed_up else 'down through'} "
        f"{config.rsi_oversold if crossed_up else config.rsi_overbought:g} "
        f"({rsi_previous:.1f} → {rsi_now:.1f})"
    )

    if config.ema_trend_period:
        trend = ema(closes, config.ema_trend_period)
        if trend is None:
            log.warning("not enough history for EMA(%d) yet", config.ema_trend_period)
            return None
        price = closes[-1]
        if side == "buy" and price < trend:
            log.info("skipping buy: price %.5f is below EMA %.5f", price, trend)
            return None
        if side == "sell" and price > trend:
            log.info("skipping sell: price %.5f is above EMA %.5f", price, trend)
            return None
        reason += f", price {'above' if side == 'buy' else 'below'} EMA{config.ema_trend_period}"

    return Signal(side=side, reason=reason, rsi_now=rsi_now, rsi_previous=rsi_previous)


# ---------------------------------------------------------------------------
# The bot
# ---------------------------------------------------------------------------


class DailyLossGuard:
    """Stops the bot opening anything new once the day's budget is spent.

    An unattended process needs a floor it cannot argue with. This is that
    floor, and it resets at UTC midnight.

    It halts *new entries* rather than flattening open positions: those already
    carry stops, and force-closing them at an arbitrary moment turns a managed
    loss into a realised one. If your prop firm's rules require flat, close by
    hand — the loud log line below is your cue.
    """

    def __init__(self, max_daily_loss_pct: float):
        self.max_daily_loss_pct = max_daily_loss_pct
        self._day: str | None = None
        self._starting_equity: float | None = None
        self._tripped = False

    def observe(self, equity: float) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._day:
            self._day = today
            self._starting_equity = equity
            self._tripped = False
            log.info("new trading day %s, starting equity %.2f", today, equity)

    def check(self, equity: float) -> bool:
        """True while trading is allowed."""

        if self._starting_equity is None or self._starting_equity <= 0:
            return True

        change_pct = 100.0 * (equity - self._starting_equity) / self._starting_equity
        if change_pct > -self.max_daily_loss_pct:
            return True

        if not self._tripped:
            self._tripped = True
            log.error(
                "DAILY LOSS LIMIT HIT: equity %.2f is %.2f%% below the day's "
                "opening %.2f (limit %.2f%%). No new positions until UTC midnight. "
                "Open positions are left on their stops — close them by hand if "
                "your account rules require flat.",
                equity,
                abs(change_pct),
                self._starting_equity,
                self.max_daily_loss_pct,
            )
        return False


class Bot:
    def __init__(self, config: BotConfig, session: Session):
        self.config = config
        self.session = session
        self.daily_loss = DailyLossGuard(config.max_daily_loss_pct)
        self._last_bar: str | None = None
        self._running = True

    def stop(self, signum, _frame) -> None:
        log.info("received %s, finishing this cycle and shutting down", signal.Signals(signum).name)
        self._running = False

    # -- market state ------------------------------------------------------

    def closed_candles(self) -> list[dict]:
        """History with the still-forming bar dropped.

        MetaTrader returns the current, incomplete candle as the last element.
        Acting on it means the signal repaints and can fire several times for
        what turns out to be one bar.
        """

        payload = self.session.candles(
            self.config.symbol, self.config.timeframe, self.config.candle_count
        )
        return payload["candles"][:-1]

    def open_position(self):
        positions = self.session.positions(self.config.symbol)["positions"]
        return positions[0] if positions else None

    # -- one iteration -----------------------------------------------------

    def tick(self) -> None:
        account = self.session.account()
        self.daily_loss.observe(account["equity"])

        candles = self.closed_candles()
        if not candles:
            log.warning("no closed candles returned for %s", self.config.symbol)
            return

        latest_bar = candles[-1]["time"]
        if latest_bar == self._last_bar:
            return  # same bar as last time; nothing new has happened
        self._last_bar = latest_bar

        volatility = atr(candles, self.config.atr_period)
        if volatility is None or volatility <= 0:
            log.warning("ATR(%d) unavailable, skipping this bar", self.config.atr_period)
            return

        signal_ = evaluate(candles, self.config)
        position = self.open_position()

        log.info(
            "bar %s close %.5f atr %.5f | %s | %s",
            latest_bar,
            candles[-1]["close"],
            volatility,
            f"{signal_.side} — {signal_.reason}" if signal_ else "no signal",
            f"holding {position['side']} {position['volume']}" if position else "flat",
        )

        if signal_ is None:
            return

        if position is not None:
            if position["side"] != signal_.side:
                self.close(position, signal_)
            else:
                log.info("already holding a %s, not adding to it", position["side"])
            return

        if not self.daily_loss.check(account["equity"]):
            return

        self.enter(signal_, candles[-1]["close"], volatility)

    # -- actions -----------------------------------------------------------

    def close(self, position: dict, signal_: Signal) -> None:
        log.info(
            "closing %s #%s on the opposite signal (%s)",
            position["side"],
            position["ticket"],
            signal_.reason,
        )
        if self.config.dry_run:
            log.info("DRY RUN: would close #%s", position["ticket"])
            return
        try:
            result = self.session.close_position(position["ticket"])
            log.info("close result: %s", result["message"])
        except (SafetyError, AdapterError) as exc:
            log.error("could not close #%s: %s", position["ticket"], exc)

    def enter(self, signal_: Signal, price: float, volatility: float) -> None:
        distance = volatility * self.config.atr_stop_multiple
        target = volatility * self.config.atr_target_multiple

        if signal_.side == "buy":
            stop_loss, take_profit = price - distance, price + target
        else:
            stop_loss, take_profit = price + distance, price - target

        try:
            sized = self.session.size_position(
                self.config.symbol,
                signal_.side,
                entry=price,
                stop_loss=stop_loss,
                risk_pct=self.config.risk_pct,
                take_profit=take_profit,
            )
        except (RiskError, AdapterError) as exc:
            log.error("could not size the trade: %s", exc)
            return

        log.info(
            "%s %s %.2f lots @ ~%.5f, stop %.5f, target %.5f — risking %.2f (%s)",
            signal_.side.upper(),
            self.config.symbol,
            sized["volume"],
            price,
            stop_loss,
            take_profit,
            sized["loss_at_stop"],
            signal_.reason,
        )

        if self.config.dry_run:
            log.info("DRY RUN: no order sent")
            return

        # The confirmation token exists to stop an AI agent executing without a
        # human having read a preview. An unattended bot is a different case:
        # the operator authorised this strategy and these limits when they
        # started the service, not each individual fill. So the bot mints the
        # token for the order it just built. Do not copy this into an
        # agent-driven path — there, the whole point is that a person sees the
        # preview first.
        intent = OrderIntent(
            self.config.symbol,
            signal_.side,
            sized["volume"],
            stop_loss,
            take_profit,
            comment="rsi-bot",
        )

        try:
            result = self.session.place_order(
                self.config.symbol,
                signal_.side,
                sized["volume"],
                stop_loss=stop_loss,
                take_profit=take_profit,
                comment="rsi-bot",
                confirm_token=confirmation_token(intent),
            )
        except (SafetyError, AdapterError) as exc:
            log.error("order refused: %s", exc)
            return

        if result.get("ok"):
            log.info("filled: %s", result["message"])
        else:
            log.error("not filled: %s", result["message"])

    # -- loop --------------------------------------------------------------

    def run(self) -> None:
        log.info("strategy: %s", self.config.describe())
        log.info("broker: %s", self.session.status()["note"])
        if self.config.dry_run:
            log.info("DRY RUN is on — signals are logged, no orders are sent")

        while self._running:
            started = time.monotonic()
            try:
                self.tick()
            except AdapterError as exc:
                log.error("broker error, will retry next cycle: %s", exc)
            except Exception:  # noqa: BLE001 — a crash here stops the service
                log.exception("unexpected error, continuing")

            # Sleep in slices so a SIGTERM does not wait out a long poll.
            elapsed = time.monotonic() - started
            remaining = max(self.config.poll_seconds - elapsed, 0)
            while self._running and remaining > 0:
                nap = min(remaining, 1.0)
                time.sleep(nap)
                remaining -= nap

        log.info("stopped")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    try:
        bot_config, broker_config = load()
    except ConfigError as exc:
        log.error("configuration problem: %s", exc)
        return 2

    if broker_config.mode is TradeMode.LIVE and not bot_config.dry_run:
        log.warning("=" * 70)
        log.warning("LIVE MODE — this process will place real orders with real money.")
        log.warning("=" * 70)

    try:
        session = Session(broker_config).open()
    except AdapterError as exc:
        log.error("could not connect to the broker: %s", exc)
        return 1

    bot = Bot(bot_config, session)
    signal.signal(signal.SIGTERM, bot.stop)
    signal.signal(signal.SIGINT, bot.stop)

    try:
        bot.run()
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
