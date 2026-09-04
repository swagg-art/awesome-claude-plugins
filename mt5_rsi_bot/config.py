"""Configuration for the RSI bot, read once from the environment.

Two namespaces are in play here, on purpose:

* ``MT5_RSI_*``   — strategy and risk settings, defined below.
* ``NATIVE_MT5_*`` — the broker connection and the hard safety caps, owned by
  the ``native_mt5`` package this bot runs on top of.

Keeping them separate means the caps that stop the bot doing damage are the
same ones the MCP server enforces, configured the same way, rather than a
second implementation that can drift.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from native_mt5.adapters.base import TIMEFRAME_MINUTES
from native_mt5.config import Config as BrokerConfig
from native_mt5.safety import TradeMode

ENV_PREFIX = "MT5_RSI_"


class ConfigError(ValueError):
    """The environment describes a bot we should not start."""


def _env(name: str, default: str = "") -> str:
    return os.environ.get(ENV_PREFIX + name, default).strip()


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{ENV_PREFIX}{name} must be a number, got {raw!r}") from exc


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{ENV_PREFIX}{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class BotConfig:
    """Everything the strategy loop needs, already validated."""

    symbol: str = "EURUSD"
    timeframe: str = "M15"

    # -- signal ------------------------------------------------------------
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    ema_trend_period: int = 0  # 0 disables the trend filter

    # -- stops and targets -------------------------------------------------
    atr_period: int = 14
    atr_stop_multiple: float = 2.0
    atr_target_multiple: float = 3.0

    # -- risk --------------------------------------------------------------
    risk_pct: float = 0.5
    max_daily_loss_pct: float = 2.0

    # -- loop --------------------------------------------------------------
    poll_seconds: int = 30
    candle_count: int = 200
    dry_run: bool = False

    @classmethod
    def from_env(cls) -> BotConfig:
        config = cls(
            symbol=(_env("SYMBOL", "EURUSD") or "EURUSD").upper(),
            timeframe=(_env("TIMEFRAME", "M15") or "M15").upper(),
            rsi_period=_env_int("RSI_PERIOD", 14),
            rsi_oversold=_env_float("RSI_OVERSOLD", 30.0),
            rsi_overbought=_env_float("RSI_OVERBOUGHT", 70.0),
            ema_trend_period=_env_int("EMA_TREND_PERIOD", 0),
            atr_period=_env_int("ATR_PERIOD", 14),
            atr_stop_multiple=_env_float("ATR_STOP_MULTIPLE", 2.0),
            atr_target_multiple=_env_float("ATR_TARGET_MULTIPLE", 3.0),
            risk_pct=_env_float("RISK_PCT", 0.5),
            max_daily_loss_pct=_env_float("MAX_DAILY_LOSS_PCT", 2.0),
            poll_seconds=_env_int("POLL_SECONDS", 30),
            candle_count=_env_int("CANDLE_COUNT", 200),
            dry_run=_env("DRY_RUN", "false").lower() in {"1", "true", "yes"},
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.timeframe not in TIMEFRAME_MINUTES:
            allowed = ", ".join(TIMEFRAME_MINUTES)
            raise ConfigError(f"TIMEFRAME must be one of: {allowed}")
        if self.rsi_period < 2:
            raise ConfigError("RSI_PERIOD must be at least 2")
        if not 0 < self.rsi_oversold < self.rsi_overbought < 100:
            raise ConfigError(
                "RSI thresholds must satisfy 0 < OVERSOLD < OVERBOUGHT < 100, got "
                f"{self.rsi_oversold} and {self.rsi_overbought}"
            )
        if self.atr_period < 2:
            raise ConfigError("ATR_PERIOD must be at least 2")
        if self.atr_stop_multiple <= 0:
            raise ConfigError("ATR_STOP_MULTIPLE must be greater than 0")
        if self.atr_target_multiple <= 0:
            raise ConfigError("ATR_TARGET_MULTIPLE must be greater than 0")
        if not 0 < self.risk_pct <= 100:
            raise ConfigError("RISK_PCT must be in (0, 100]")
        if not 0 < self.max_daily_loss_pct <= 100:
            raise ConfigError("MAX_DAILY_LOSS_PCT must be in (0, 100]")
        if self.poll_seconds < 1:
            raise ConfigError("POLL_SECONDS must be at least 1")
        if self.ema_trend_period and self.ema_trend_period < 2:
            raise ConfigError("EMA_TREND_PERIOD must be 0 (off) or at least 2")

        # Enough history for the slowest indicator plus its warm-up.
        needed = max(self.rsi_period, self.atr_period, self.ema_trend_period) * 3
        if self.candle_count < needed:
            raise ConfigError(
                f"CANDLE_COUNT of {self.candle_count} is too small for these "
                f"periods; use at least {needed}"
            )

    def describe(self) -> str:
        trend = (
            f"EMA{self.ema_trend_period} trend filter"
            if self.ema_trend_period
            else "no trend filter"
        )
        return (
            f"{self.symbol} {self.timeframe} | "
            f"RSI({self.rsi_period}) {self.rsi_oversold:g}/{self.rsi_overbought:g} | "
            f"{trend} | "
            f"stop {self.atr_stop_multiple:g}xATR({self.atr_period}), "
            f"target {self.atr_target_multiple:g}xATR | "
            f"risk {self.risk_pct:g}%/trade, {self.max_daily_loss_pct:g}%/day"
        )


def load() -> tuple[BotConfig, BrokerConfig]:
    """Load both halves of the configuration and cross-check them."""

    bot = BotConfig.from_env()
    broker = BrokerConfig.from_env()

    if broker.mode is TradeMode.READONLY and not bot.dry_run:
        raise ConfigError(
            "NATIVE_MT5_MODE is readonly, so the bot could never place an order. "
            "Set it to paper to simulate, live to trade for real, or set "
            "MT5_RSI_DRY_RUN=true to run the strategy for its logs alone."
        )

    if bot.risk_pct > broker.max_risk_per_trade_pct:
        raise ConfigError(
            f"MT5_RSI_RISK_PCT ({bot.risk_pct}%) exceeds the broker-side ceiling "
            f"NATIVE_MT5_MAX_RISK_PER_TRADE_PCT ({broker.max_risk_per_trade_pct}%). "
            "Raise the ceiling deliberately or lower the bot's risk."
        )

    if broker.symbol_allowlist and bot.symbol not in broker.symbol_allowlist:
        allowed = ", ".join(broker.symbol_allowlist)
        raise ConfigError(
            f"MT5_RSI_SYMBOL is {bot.symbol}, which is not in "
            f"NATIVE_MT5_SYMBOL_ALLOWLIST ({allowed})"
        )

    return bot, broker
