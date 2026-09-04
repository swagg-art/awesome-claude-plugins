"""Runtime configuration, read once from the environment.

Every setting has a safe default: with no environment at all the server comes
up against the mock adapter in read-only mode, which is what we want for a
first run, for CI, and for anyone poking at the tools before wiring a broker.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .safety import TradeMode

ENV_PREFIX = "NATIVE_MT5_"


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


class ConfigError(ValueError):
    """Raised when the environment describes a configuration we cannot honour."""


@dataclass(frozen=True)
class TerminalCredentials:
    """Login details for a MetaTrader 5 terminal.

    All three are optional: an already-logged-in terminal on the same machine
    is picked up without them.
    """

    login: int | None = None
    password: str = ""
    server: str = ""
    terminal_path: str = ""

    @property
    def is_complete(self) -> bool:
        return bool(self.login and self.password and self.server)


@dataclass(frozen=True)
class Config:
    adapter: str = "mock"
    mode: TradeMode = TradeMode.READONLY
    credentials: TerminalCredentials = field(default_factory=TerminalCredentials)
    magic: int = 777001
    deviation_points: int = 20
    max_risk_per_trade_pct: float = 1.0
    max_order_volume: float = 1.0
    max_open_positions: int = 10
    symbol_allowlist: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> Config:
        adapter = (_env("ADAPTER", "mock") or "mock").lower()
        if adapter not in {"mock", "terminal"}:
            raise ConfigError(
                f"{ENV_PREFIX}ADAPTER must be 'mock' or 'terminal', got {adapter!r}"
            )

        mode = TradeMode.parse(_env("MODE", TradeMode.READONLY.value))

        login_raw = _env("LOGIN")
        credentials = TerminalCredentials(
            login=int(login_raw) if login_raw else None,
            password=_env("PASSWORD"),
            server=_env("SERVER"),
            terminal_path=_env("TERMINAL_PATH"),
        )

        allowlist = tuple(
            s.strip().upper() for s in _env("SYMBOL_ALLOWLIST").split(",") if s.strip()
        )

        config = cls(
            adapter=adapter,
            mode=mode,
            credentials=credentials,
            magic=_env_int("MAGIC", 777001),
            deviation_points=_env_int("DEVIATION_POINTS", 20),
            max_risk_per_trade_pct=_env_float("MAX_RISK_PER_TRADE_PCT", 1.0),
            max_order_volume=_env_float("MAX_ORDER_VOLUME", 1.0),
            max_open_positions=_env_int("MAX_OPEN_POSITIONS", 10),
            symbol_allowlist=allowlist,
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.max_risk_per_trade_pct <= 0 or self.max_risk_per_trade_pct > 100:
            raise ConfigError("MAX_RISK_PER_TRADE_PCT must be in (0, 100]")
        if self.max_order_volume <= 0:
            raise ConfigError("MAX_ORDER_VOLUME must be greater than 0")
        if self.max_open_positions < 0:
            raise ConfigError("MAX_OPEN_POSITIONS cannot be negative")
        if self.mode is TradeMode.LIVE and self.adapter == "mock":
            raise ConfigError(
                "live mode against the mock adapter is meaningless — "
                f"set {ENV_PREFIX}ADAPTER=terminal or drop back to readonly/paper"
            )

    def describe(self) -> dict[str, object]:
        """Config as shown to the model — never includes the password."""
        return {
            "adapter": self.adapter,
            "mode": self.mode.value,
            "login": self.credentials.login,
            "server": self.credentials.server or None,
            "magic": self.magic,
            "max_risk_per_trade_pct": self.max_risk_per_trade_pct,
            "max_order_volume": self.max_order_volume,
            "max_open_positions": self.max_open_positions,
            "symbol_allowlist": list(self.symbol_allowlist) or "all symbols",
        }
