"""A deterministic synthetic broker.

This is what runs when nobody has wired a terminal yet — on CI, on macOS and
Linux where the MetaTrader5 package will not install, and any time someone
wants to see what the tools return before trusting them with an account.

Prices come from a seeded random walk, so the same symbol and timeframe always
produce the same series. Nothing here talks to a network.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta
from itertools import count

from ..safety import TradeMode
from .base import (
    TIMEFRAME_MINUTES,
    Account,
    AdapterError,
    Candle,
    Deal,
    OrderResult,
    Position,
    Quote,
    SymbolInfo,
    normalise_timeframe,
)

# Contract specs close enough to a real retail broker to make sizing realistic.
_SPECS: dict[str, dict] = {
    "EURUSD": dict(desc="Euro vs US Dollar", price=1.0850, digits=5, tick_value=1.0, vol=0.0006),
    "GBPUSD": dict(desc="Pound vs US Dollar", price=1.2670, digits=5, tick_value=1.0, vol=0.0008),
    "USDJPY": dict(desc="US Dollar vs Yen", price=151.20, digits=3, tick_value=0.67, vol=0.09),
    "XAUUSD": dict(desc="Gold vs US Dollar", price=2340.00, digits=2, tick_value=1.0, vol=6.5),
    "BTCUSD": dict(desc="Bitcoin vs US Dollar", price=64200.0, digits=2, tick_value=1.0, vol=850.0),
    "US500": dict(desc="S&P 500 Index", price=5230.0, digits=1, tick_value=1.0, vol=18.0),
}


class MockAdapter:
    """Implements the Adapter protocol against synthetic data."""

    name = "mock"

    def __init__(self, mode: TradeMode = TradeMode.READONLY, balance: float = 10_000.0):
        self._mode = mode
        self._balance = balance
        self._connected = False
        self._tickets = count(500_001)
        self._positions: dict[int, Position] = {}
        self._deals: list[Deal] = []

    # -- lifecycle ---------------------------------------------------------

    def connect(self) -> None:
        self._connected = True

    def close(self) -> None:
        self._connected = False

    def _require_connection(self) -> None:
        if not self._connected:
            raise AdapterError("adapter is not connected — call connect() first")

    # -- account -----------------------------------------------------------

    def account(self) -> Account:
        self._require_connection()
        floating = round(sum(p.profit for p in self._positions.values()), 2)
        margin = round(sum(p.volume for p in self._positions.values()) * 300.0, 2)
        equity = round(self._balance + floating, 2)
        return Account(
            login=9_000_001,
            name="Native MT5 Demo",
            server="NativeMT5-Mock",
            currency="USD",
            balance=round(self._balance, 2),
            equity=equity,
            margin=margin,
            margin_free=round(equity - margin, 2),
            margin_level=round(100 * equity / margin, 2) if margin else 0.0,
            leverage=100,
            profit=floating,
        )

    # -- instruments -------------------------------------------------------

    def symbols(self, search: str = "") -> list[SymbolInfo]:
        self._require_connection()
        needle = (search or "").strip().upper()
        return [self.symbol(name) for name in sorted(_SPECS) if needle in name]

    def symbol(self, name: str) -> SymbolInfo:
        self._require_connection()
        key = (name or "").strip().upper()
        spec = _SPECS.get(key)
        if spec is None:
            known = ", ".join(sorted(_SPECS))
            raise AdapterError(f"unknown symbol {name!r}; the mock broker offers: {known}")
        point = 10.0 ** -spec["digits"]
        return SymbolInfo(
            name=key,
            description=spec["desc"],
            digits=spec["digits"],
            point=point,
            tick_size=point,
            tick_value=spec["tick_value"],
            contract_size=100_000.0 if key.endswith("USD") and len(key) == 6 else 1.0,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            currency_profit="USD",
        )

    # -- prices ------------------------------------------------------------

    def _series(self, symbol: str, timeframe: str, count_: int) -> list[Candle]:
        info = self.symbol(symbol)
        spec = _SPECS[info.name]
        minutes = TIMEFRAME_MINUTES[timeframe]

        rng = random.Random(f"{info.name}:{timeframe}")
        step_vol = spec["vol"] * math.sqrt(minutes / 60.0)
        price = spec["price"]
        # Walk backwards from a fixed anchor so the series never shifts under a
        # caller between two calls in the same session.
        anchor = datetime(2026, 1, 1, tzinfo=UTC)

        candles: list[Candle] = []
        for i in range(count_):
            drift = rng.gauss(0, step_vol)
            open_ = price
            close = max(open_ + drift, info.point)
            high = max(open_, close) + abs(rng.gauss(0, step_vol / 3))
            low = max(min(open_, close) - abs(rng.gauss(0, step_vol / 3)), info.point)
            price = close
            when = anchor - timedelta(minutes=minutes * (count_ - i))
            candles.append(
                Candle(
                    time=when.isoformat(),
                    open=round(open_, info.digits),
                    high=round(high, info.digits),
                    low=round(low, info.digits),
                    close=round(close, info.digits),
                    tick_volume=rng.randint(120, 4200),
                )
            )
        return candles

    def candles(self, symbol: str, timeframe: str, count_: int = 100) -> list[Candle]:
        self._require_connection()
        timeframe = normalise_timeframe(timeframe)
        if count_ < 1 or count_ > 5000:
            raise AdapterError("count must be between 1 and 5000")
        return self._series(symbol, timeframe, count_)

    def quote(self, symbol: str) -> Quote:
        self._require_connection()
        info = self.symbol(symbol)
        last = self._series(info.name, "M1", 1)[-1]
        half_spread = info.point * (10 if info.digits >= 3 else 2)
        return Quote(
            symbol=info.name,
            time=datetime.now(UTC).isoformat(),
            bid=round(last.close - half_spread, info.digits),
            ask=round(last.close + half_spread, info.digits),
        )

    # -- positions and history --------------------------------------------

    def positions(self, symbol: str = "") -> list[Position]:
        self._require_connection()
        needle = (symbol or "").strip().upper()
        found = [p for p in self._positions.values() if not needle or p.symbol == needle]
        return [self._marked_to_market(p) for p in found]

    def _marked_to_market(self, position: Position) -> Position:
        info = self.symbol(position.symbol)
        quote = self.quote(position.symbol)
        current = quote.bid if position.side == "buy" else quote.ask
        direction = 1 if position.side == "buy" else -1
        move = (current - position.open_price) * direction
        profit = (move / info.tick_size) * info.tick_value * position.volume
        return Position(
            ticket=position.ticket,
            symbol=position.symbol,
            side=position.side,
            volume=position.volume,
            open_price=position.open_price,
            current_price=current,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            profit=round(profit, 2),
            opened_at=position.opened_at,
            comment=position.comment,
        )

    def history(self, days: int = 30) -> list[Deal]:
        self._require_connection()
        cutoff = datetime.now(UTC) - timedelta(days=days)
        return [d for d in self._deals if datetime.fromisoformat(d.time) >= cutoff]

    # -- writes ------------------------------------------------------------

    def place_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "",
    ) -> OrderResult:
        self._require_connection()
        info = self.symbol(symbol)
        quote = self.quote(info.name)
        price = quote.ask if side == "buy" else quote.bid
        ticket = next(self._tickets)
        self._positions[ticket] = Position(
            ticket=ticket,
            symbol=info.name,
            side=side,
            volume=volume,
            open_price=price,
            current_price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            profit=0.0,
            opened_at=datetime.now(UTC).isoformat(),
            comment=comment,
        )
        return OrderResult(
            ok=True,
            ticket=ticket,
            price=price,
            volume=volume,
            message=f"simulated {side} {volume} {info.name} at {price}",
            simulated=True,
        )

    def close_position(self, ticket: int) -> OrderResult:
        self._require_connection()
        position = self._positions.pop(ticket, None)
        if position is None:
            raise AdapterError(f"no open position with ticket {ticket}")
        settled = self._marked_to_market(position)
        self._balance += settled.profit
        self._deals.append(
            Deal(
                ticket=ticket,
                symbol=settled.symbol,
                side="sell" if settled.side == "buy" else "buy",
                volume=settled.volume,
                price=settled.current_price,
                profit=settled.profit,
                commission=round(-0.7 * settled.volume, 2),
                swap=0.0,
                time=datetime.now(UTC).isoformat(),
            )
        )
        return OrderResult(
            ok=True,
            ticket=ticket,
            price=settled.current_price,
            volume=settled.volume,
            message=f"simulated close of {ticket} for {settled.profit:+.2f} USD",
            simulated=True,
        )
