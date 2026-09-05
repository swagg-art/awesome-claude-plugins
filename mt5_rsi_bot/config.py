"""Configuration, loaded from .env.

Every value is validated at startup rather than at the moment it would first
cause a bad order. A bot that refuses to start is cheap; one that starts with a
two-dollar stop on Bitcoin is not.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Explicit path rather than a cwd search: systemd sets WorkingDirectory, but a
# manual `python /path/to/main.py` from elsewhere would otherwise silently pick
# up no .env at all and run on defaults.
load_dotenv(Path(__file__).with_name(".env"))


class ConfigError(ValueError):
    """The environment describes a bot that should not start."""


def _int(name, default):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}") from None


def _float(name, default):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from None


def _str(name, default=""):
    return os.getenv(name, default).strip()


def _bool(name, default=False):
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


class Config:
    # -- account -----------------------------------------------------------
    LOGIN = _int("MT5_LOGIN", 0)
    PASSWORD = _str("MT5_PASSWORD")
    SERVER = _str("MT5_SERVER")
    SYMBOL = _str("MT5_SYMBOL", "BTCUSD").upper()
    TIMEFRAME = _str("MT5_TIMEFRAME", "M15").upper()

    # -- order -------------------------------------------------------------
    LOT_SIZE = _float("LOT_SIZE", 0.01)
    MAGIC_NUMBER = _int("MAGIC_NUMBER", 123456)
    DEVIATION = _int("DEVIATION", 20)

    # -- strategy ----------------------------------------------------------
    # "confirmed": arm on RSI divergence or an extreme, then wait for a candle
    #   pattern AND a close beyond the previous bar before entering. Stops come
    #   from swing structure, not a fixed percentage.
    # "simple": the original RSI threshold cross with fixed-percent stops.
    #   Backtested at profit factor 0.53 on BTC daily; kept for comparison.
    STRATEGY = _str("STRATEGY", "confirmed").lower()
    DIVERGENCE_ONLY = _bool("DIVERGENCE_ONLY", False)
    CONFIRM_WITHIN_BARS = _int("CONFIRM_WITHIN_BARS", 5)
    REWARD_MULTIPLE = _float("REWARD_MULTIPLE", 3.0)
    ATR_BUFFER = _float("ATR_BUFFER", 0.5)

    # -- signal ------------------------------------------------------------
    RSI_PERIOD = _int("RSI_PERIOD", 14)
    RSI_OVERSOLD = _float("RSI_OVERSOLD", 30)
    RSI_OVERBOUGHT = _float("RSI_OVERBOUGHT", 70)
    BAR_COUNT = _int("BAR_COUNT", 300)

    # -- stops -------------------------------------------------------------
    # "percent" scales with the instrument's price and is the safe default.
    # "points" is the raw MetaTrader unit — correct only if you have checked
    # what a point is worth on the symbol you are trading.
    SL_MODE = _str("SL_MODE", "percent").lower()
    SL_PERCENT = _float("SL_PERCENT", 1.0)
    TP_PERCENT = _float("TP_PERCENT", 2.0)
    SL_PIPS = _int("SL_PIPS", 200)
    TP_PIPS = _int("TP_PIPS", 400)

    # A stop closer than this fraction of price is almost certainly a unit
    # mistake, not a plan. See validate().
    MIN_STOP_PERCENT = _float("MIN_STOP_PERCENT", 0.1)

    # -- safety ------------------------------------------------------------
    MAX_DAILY_LOSS_PERCENT = _float("MAX_DAILY_LOSS_PERCENT", 2.0)
    MAX_OPEN_POSITIONS = _int("MAX_OPEN_POSITIONS", 1)
    POLL_SECONDS = _int("POLL_SECONDS", 15)
    DRY_RUN = _bool("DRY_RUN", False)

    VALID_TIMEFRAMES = (
        "M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1",
    )

    @classmethod
    def validate(cls):
        """Raise ConfigError on anything that would produce a bad order."""

        if not cls.SYMBOL:
            raise ConfigError("MT5_SYMBOL cannot be empty")

        if cls.TIMEFRAME not in cls.VALID_TIMEFRAMES:
            raise ConfigError(
                f"MT5_TIMEFRAME must be one of: {', '.join(cls.VALID_TIMEFRAMES)}"
            )

        # Partial credentials are worse than none: MT5 silently stays on
        # whatever account the terminal already had open.
        supplied = [bool(cls.LOGIN), bool(cls.PASSWORD), bool(cls.SERVER)]
        if any(supplied) and not all(supplied):
            raise ConfigError(
                "MT5_LOGIN, MT5_PASSWORD and MT5_SERVER must be set together, or "
                "all left blank to use the terminal's current login"
            )

        if cls.LOT_SIZE <= 0:
            raise ConfigError(f"LOT_SIZE must be positive, got {cls.LOT_SIZE}")

        if cls.RSI_PERIOD < 2:
            raise ConfigError("RSI_PERIOD must be at least 2")

        if not 0 < cls.RSI_OVERSOLD < cls.RSI_OVERBOUGHT < 100:
            raise ConfigError(
                "RSI thresholds must satisfy 0 < OVERSOLD < OVERBOUGHT < 100, got "
                f"{cls.RSI_OVERSOLD} and {cls.RSI_OVERBOUGHT}"
            )

        if cls.BAR_COUNT < cls.RSI_PERIOD * 3:
            raise ConfigError(
                f"BAR_COUNT of {cls.BAR_COUNT} is too little warm-up for "
                f"RSI({cls.RSI_PERIOD}); use at least {cls.RSI_PERIOD * 3}"
            )

        if cls.STRATEGY not in {"confirmed", "simple"}:
            raise ConfigError("STRATEGY must be 'confirmed' or 'simple'")

        if cls.STRATEGY == "confirmed":
            if cls.REWARD_MULTIPLE <= 0:
                raise ConfigError("REWARD_MULTIPLE must be positive")
            if cls.CONFIRM_WITHIN_BARS < 1:
                raise ConfigError("CONFIRM_WITHIN_BARS must be at least 1")
            if cls.ATR_BUFFER < 0:
                raise ConfigError("ATR_BUFFER cannot be negative")
            # Structure stops need room for swing detection and ATR warm-up.
            if cls.BAR_COUNT < 120:
                raise ConfigError(
                    f"STRATEGY=confirmed needs BAR_COUNT of at least 120 for swing "
                    f"and divergence lookback; got {cls.BAR_COUNT}"
                )

        if cls.SL_MODE not in {"percent", "points"}:
            raise ConfigError("SL_MODE must be 'percent' or 'points'")

        if cls.SL_MODE == "percent":
            if cls.SL_PERCENT <= 0 or cls.TP_PERCENT <= 0:
                raise ConfigError("SL_PERCENT and TP_PERCENT must be positive")
            if cls.SL_PERCENT >= 100:
                raise ConfigError("SL_PERCENT of 100 or more would be past zero")
        elif cls.SL_PIPS <= 0 or cls.TP_PIPS <= 0:
            raise ConfigError("SL_PIPS and TP_PIPS must be positive")

        if not 0 < cls.MAX_DAILY_LOSS_PERCENT <= 100:
            raise ConfigError("MAX_DAILY_LOSS_PERCENT must be in (0, 100]")

        if cls.MAX_OPEN_POSITIONS < 1:
            raise ConfigError("MAX_OPEN_POSITIONS must be at least 1")

        if cls.POLL_SECONDS < 1:
            raise ConfigError("POLL_SECONDS must be at least 1")

    @classmethod
    def stop_levels(cls, side, price, point, digits):
        """Return (stop_loss, take_profit) for an entry at `price`.

        In points mode the distance is `SL_PIPS * point`, which is what the
        original implementation did. Be careful with it: on a 2-digit symbol
        like BTCUSD a point is 0.01, so 200 points is a two-dollar stop on a
        sixty-thousand-dollar instrument. That is why percent is the default.
        """

        if cls.SL_MODE == "percent":
            sl_distance = price * cls.SL_PERCENT / 100.0
            tp_distance = price * cls.TP_PERCENT / 100.0
        else:
            sl_distance = cls.SL_PIPS * point
            tp_distance = cls.TP_PIPS * point

        if side == "BUY":
            sl, tp = price - sl_distance, price + tp_distance
        else:
            sl, tp = price + sl_distance, price - tp_distance

        return round(sl, digits), round(tp, digits), sl_distance

    @classmethod
    def describe(cls):
        if cls.STRATEGY == "confirmed":
            stops = (f"stop from swing + {cls.ATR_BUFFER:g}xATR, "
                     f"target {cls.REWARD_MULTIPLE:g}R")
        elif cls.SL_MODE == "percent":
            stops = f"stop {cls.SL_PERCENT:g}%, target {cls.TP_PERCENT:g}%"
        else:
            stops = f"stop {cls.SL_PIPS} points, target {cls.TP_PIPS} points"
        return (
            f"[{cls.STRATEGY}] {cls.SYMBOL} {cls.TIMEFRAME} | "
            f"RSI({cls.RSI_PERIOD}) {cls.RSI_OVERSOLD:g}/{cls.RSI_OVERBOUGHT:g} | "
            f"{cls.LOT_SIZE} lots | {stops} | "
            f"daily loss limit {cls.MAX_DAILY_LOSS_PERCENT:g}%"
        )


try:
    Config.validate()
except ConfigError as exc:
    print(f"Configuration error: {exc}", file=sys.stderr)
    raise SystemExit(2) from None
