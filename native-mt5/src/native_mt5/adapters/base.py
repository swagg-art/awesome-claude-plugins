"""The shape every adapter presents to the tool layer.

Deliberately narrow and made of plain dataclasses: the MCP tools serialise
these straight to JSON, and the mock adapter has to be able to produce all of
them without a terminal anywhere in sight.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol, runtime_checkable

TIMEFRAMES = (
    "M1",
    "M5",
    "M15",
    "M30",
    "H1",
    "H4",
    "D1",
    "W1",
    "MN1",
)

TIMEFRAME_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
    "W1": 10080,
    "MN1": 43200,
}


class AdapterError(RuntimeError):
    """The backend refused or could not answer a request."""


@dataclass(frozen=True)
class Account:
    login: int
    name: str
    server: str
    currency: str
    balance: float
    equity: float
    margin: float
    margin_free: float
    margin_level: float
    leverage: int
    profit: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SymbolInfo:
    """Contract specification — everything position sizing needs."""

    name: str
    description: str
    digits: int
    point: float
    tick_size: float
    tick_value: float
    contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    currency_profit: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Quote:
    symbol: str
    time: str
    bid: float
    ask: float

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    def to_dict(self) -> dict:
        data = asdict(self)
        data["spread"] = round(self.spread, 8)
        return data


@dataclass(frozen=True)
class Candle:
    time: str
    open: float
    high: float
    low: float
    close: float
    tick_volume: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Position:
    ticket: int
    symbol: str
    side: str
    volume: float
    open_price: float
    current_price: float
    stop_loss: float | None
    take_profit: float | None
    profit: float
    opened_at: str
    comment: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Deal:
    ticket: int
    symbol: str
    side: str
    volume: float
    price: float
    profit: float
    commission: float
    swap: float
    time: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OrderResult:
    ok: bool
    ticket: int | None
    price: float | None
    volume: float | None
    message: str
    simulated: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@runtime_checkable
class Adapter(Protocol):
    """What the tool layer is allowed to assume about a backend."""

    name: str

    def connect(self) -> None: ...

    def close(self) -> None: ...

    def account(self) -> Account: ...

    def symbols(self, search: str = "") -> list[SymbolInfo]: ...

    def symbol(self, name: str) -> SymbolInfo: ...

    def quote(self, symbol: str) -> Quote: ...

    def candles(self, symbol: str, timeframe: str, count: int) -> list[Candle]: ...

    def positions(self, symbol: str = "") -> list[Position]: ...

    def history(self, days: int) -> list[Deal]: ...

    def place_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        stop_loss: float | None,
        take_profit: float | None,
        comment: str,
    ) -> OrderResult: ...

    def close_position(self, ticket: int) -> OrderResult: ...


def normalise_timeframe(timeframe: str) -> str:
    value = (timeframe or "").strip().upper()
    if value not in TIMEFRAME_MINUTES:
        allowed = ", ".join(TIMEFRAMES)
        raise AdapterError(f"unknown timeframe {timeframe!r}; expected one of: {allowed}")
    return value
