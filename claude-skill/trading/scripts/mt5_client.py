"""Thin, validated wrapper over the MetaTrader5 Python API.

The real `MetaTrader5` package is imported lazily so this module can be tested,
and its constants are mirrored here so callers never need to import it.

Design: orders are sent as soon as they are asked for. What happens first is
*validation*, not confirmation - symbol resolvable, volume on the broker's
step, filling mode the broker actually accepts, stops outside the freeze
distance. A rejected order should fail here with a readable reason rather than
come back as retcode 10014 from the server.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

# --- MT5 constants (mirrored so tests and callers need no terminal) ---------

TRADE_ACTION_DEAL = 1
TRADE_ACTION_PENDING = 5
TRADE_ACTION_SLTP = 6
TRADE_ACTION_MODIFY = 7
TRADE_ACTION_REMOVE = 8

ORDER_TYPE_BUY = 0
ORDER_TYPE_SELL = 1
ORDER_TYPE_BUY_LIMIT = 2
ORDER_TYPE_SELL_LIMIT = 3
ORDER_TYPE_BUY_STOP = 4
ORDER_TYPE_SELL_STOP = 5

ORDER_TYPE_NAMES = {
    ORDER_TYPE_BUY: "buy",
    ORDER_TYPE_SELL: "sell",
    ORDER_TYPE_BUY_LIMIT: "buy limit",
    ORDER_TYPE_SELL_LIMIT: "sell limit",
    ORDER_TYPE_BUY_STOP: "buy stop",
    ORDER_TYPE_SELL_STOP: "sell stop",
}

PENDING_TYPES = {
    ("buy", "limit"): ORDER_TYPE_BUY_LIMIT,
    ("sell", "limit"): ORDER_TYPE_SELL_LIMIT,
    ("buy", "stop"): ORDER_TYPE_BUY_STOP,
    ("sell", "stop"): ORDER_TYPE_SELL_STOP,
}

ORDER_TIME_GTC = 0
ORDER_FILLING_FOK = 0
ORDER_FILLING_IOC = 1
ORDER_FILLING_RETURN = 2

SYMBOL_FILLING_FOK = 1
SYMBOL_FILLING_IOC = 2

TIMEFRAMES = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 16385, "H4": 16388,
    "D1": 16408, "W1": 32769, "MN1": 49153,
}

TRADE_RETCODE_DONE = 10009
TRADE_RETCODE_PLACED = 10008

RETCODES = {
    10004: "requote - price moved, retry with a fresh quote or wider deviation",
    10006: "request rejected by the dealer",
    10007: "request cancelled by the trader",
    10008: "order placed (pending order accepted)",
    10009: "done",
    10010: "done partially - part of the volume filled",
    10011: "request processing error",
    10012: "request timed out",
    10013: "invalid request - malformed fields",
    10014: "invalid volume - check volume_min, volume_max and volume_step",
    10015: "invalid price",
    10016: "invalid stops - SL/TP too close to price or on the wrong side",
    10017: "trade disabled for this account",
    10018: "market closed",
    10019: "not enough money for this volume",
    10020: "prices changed",
    10021: "no quotes to process the request",
    10025: "order state changed",
    10026: "autotrading disabled by the server",
    10027: "autotrading disabled in the terminal - enable the Algo Trading button",
    10030: "unsupported filling mode - the broker does not accept this fill policy",
    10031: "no connection to the trade server",
    10034: "not enough free margin",
}


class MT5Error(Exception):
    """A failure to reach, validate against, or trade through the terminal."""


class OrderRejected(MT5Error):
    def __init__(self, retcode: int, comment: str = ""):
        self.retcode = retcode
        reason = RETCODES.get(retcode, "unknown retcode")
        detail = f" ({comment})" if comment else ""
        super().__init__(f"retcode {retcode}: {reason}{detail}")


def as_dict(row) -> dict:
    """MT5 returns namedtuples; be tolerant of anything dict-shaped too."""
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "_asdict"):
        return row._asdict()
    raise MT5Error(f"unexpected record from the terminal: {type(row).__name__}")


# --- config ----------------------------------------------------------------

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.config/mt5-trading/config.json")


@dataclass
class Config:
    """Account credentials plus the limits that bound every order."""

    login: int | None = None
    password: str | None = None
    server: str | None = None
    terminal_path: str | None = None
    max_volume: float = 1.0
    max_open_positions: int = 20
    allowed_symbols: list = field(default_factory=list)
    default_deviation: int = 20
    magic: int = 777001
    dry_run: bool = False

    @classmethod
    def load(cls, path: str | None = None) -> "Config":
        path = os.path.expanduser(path or os.environ.get("MT5_CONFIG", DEFAULT_CONFIG_PATH))
        data: dict = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        env = {
            "login": os.environ.get("MT5_LOGIN"),
            "password": os.environ.get("MT5_PASSWORD"),
            "server": os.environ.get("MT5_SERVER"),
        }
        for key, value in env.items():
            if value:
                data[key] = value
        if data.get("login"):
            data["login"] = int(data["login"])
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})


# --- connection ------------------------------------------------------------

_backend = None


def set_backend(module) -> None:
    """Inject a MetaTrader5-compatible module (used by the tests)."""
    global _backend
    _backend = module


def backend():
    global _backend
    if _backend is None:
        try:
            import MetaTrader5
        except ImportError as exc:
            raise MT5Error(
                "the MetaTrader5 package is not installed. It is Windows-only: "
                "pip install MetaTrader5, and run it on the machine hosting the "
                "MT5 terminal (see reference/setup.md for macOS options)."
            ) from exc
        _backend = MetaTrader5
    return _backend


class MT5:
    """A connected terminal session."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.mt5 = backend()
        self._connected = False

    # -- lifecycle ---------------------------------------------------------
    def connect(self) -> "MT5":
        kwargs = {}
        if self.config.terminal_path:
            kwargs["path"] = self.config.terminal_path
        if self.config.login:
            kwargs.update(
                login=self.config.login,
                password=self.config.password,
                server=self.config.server,
            )
        if not self.mt5.initialize(**kwargs):
            code, message = self.mt5.last_error()
            raise MT5Error(
                f"could not initialize the terminal ({code}: {message}). "
                "Is MT5 running and logged in, with Algo Trading enabled?"
            )
        self._connected = True
        return self

    def close(self) -> None:
        if self._connected:
            self.mt5.shutdown()
            self._connected = False

    def __enter__(self) -> "MT5":
        return self.connect()

    def __exit__(self, *exc) -> None:
        self.close()

    # -- account -----------------------------------------------------------
    def account(self) -> dict:
        info = self.mt5.account_info()
        if info is None:
            raise MT5Error("no account info - the terminal is not logged in")
        data = as_dict(info)
        server = str(data.get("server", "")).lower()
        data["is_demo"] = "demo" in server or data.get("trade_mode", 0) == 0
        return data

    # -- symbols -----------------------------------------------------------
    def resolve_symbol(self, symbol: str) -> str:
        """Map a plain name onto whatever this broker actually calls it.

        Brokers suffix symbols (EURUSD.raw, EURUSD_i, EURUSDm). An exact match
        wins; otherwise a unique prefix match is accepted.
        """
        symbol = symbol.upper().strip()
        if self.mt5.symbol_info(symbol) is not None:
            return symbol
        candidates = [
            s.name for s in (self.mt5.symbols_get() or []) if s.name.upper().startswith(symbol)
        ]
        exact = [c for c in candidates if c.upper() == symbol]
        if exact:
            return exact[0]
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise MT5Error(f"unknown symbol {symbol!r} on this broker")
        raise MT5Error(
            f"ambiguous symbol {symbol!r} - candidates: {', '.join(sorted(candidates)[:8])}"
        )

    def symbol(self, name: str):
        resolved = self.resolve_symbol(name)
        info = self.mt5.symbol_info(resolved)
        if info is None:
            raise MT5Error(f"no symbol info for {resolved}")
        if not info.visible and not self.mt5.symbol_select(resolved, True):
            raise MT5Error(f"could not select {resolved} in Market Watch")
        return info

    def tick(self, name: str):
        resolved = self.resolve_symbol(name)
        tick = self.mt5.symbol_info_tick(resolved)
        if tick is None or (tick.bid == 0 and tick.ask == 0):
            raise MT5Error(f"no quotes for {resolved} - market may be closed")
        return tick

    # -- validation --------------------------------------------------------
    def check_symbol_allowed(self, resolved: str) -> None:
        allowed = self.config.allowed_symbols
        if allowed and not any(resolved.upper().startswith(a.upper()) for a in allowed):
            raise MT5Error(
                f"{resolved} is not in allowed_symbols {allowed} - widen the config to trade it"
            )

    def normalize_volume(self, info, volume: float) -> float:
        """Round to the broker's lot step and bound-check, including our own cap."""
        step = info.volume_step or 0.01
        normalized = round(round(volume / step) * step, 8)
        if normalized < info.volume_min:
            raise MT5Error(f"volume {volume} is below {info.name} minimum {info.volume_min}")
        if normalized > info.volume_max:
            raise MT5Error(f"volume {volume} is above {info.name} maximum {info.volume_max}")
        if self.config.max_volume and normalized > self.config.max_volume:
            raise MT5Error(
                f"volume {normalized} exceeds max_volume {self.config.max_volume} in your config"
            )
        return normalized

    def filling_mode(self, info) -> int:
        """Pick a fill policy the broker accepts (retcode 10030 otherwise)."""
        mask = getattr(info, "filling_mode", 0)
        if mask & SYMBOL_FILLING_IOC:
            return ORDER_FILLING_IOC
        if mask & SYMBOL_FILLING_FOK:
            return ORDER_FILLING_FOK
        return ORDER_FILLING_RETURN

    def check_stops(self, info, side, price, sl, tp) -> None:
        """SL/TP must sit on the right side and outside the broker's stop level."""
        point = info.point or 0.00001
        min_distance = (getattr(info, "trade_stops_level", 0) or 0) * point
        if sl is not None:
            if side == "buy" and sl >= price:
                raise MT5Error(f"buy stop-loss {sl} must be below entry {price}")
            if side == "sell" and sl <= price:
                raise MT5Error(f"sell stop-loss {sl} must be above entry {price}")
            if min_distance and abs(price - sl) < min_distance:
                raise MT5Error(
                    f"stop-loss is {abs(price - sl):.5f} from price; "
                    f"{info.name} requires at least {min_distance:.5f}"
                )
        if tp is not None:
            if side == "buy" and tp <= price:
                raise MT5Error(f"buy take-profit {tp} must be above entry {price}")
            if side == "sell" and tp >= price:
                raise MT5Error(f"sell take-profit {tp} must be below entry {price}")
            if min_distance and abs(price - tp) < min_distance:
                raise MT5Error(
                    f"take-profit is {abs(price - tp):.5f} from price; "
                    f"{info.name} requires at least {min_distance:.5f}"
                )

    # -- sending -----------------------------------------------------------
    def _send(self, request: dict, retries: int = 2) -> dict:
        if self.config.dry_run:
            return {"dry_run": True, "request": request, "retcode": TRADE_RETCODE_DONE}
        last = None
        for attempt in range(retries + 1):
            result = self.mt5.order_send(request)
            if result is None:
                code, message = self.mt5.last_error()
                raise MT5Error(f"order_send returned nothing ({code}: {message})")
            data = as_dict(result)
            if data["retcode"] in (TRADE_RETCODE_DONE, TRADE_RETCODE_PLACED):
                return data
            # a requote or a moved price is worth one refreshed retry
            if data["retcode"] in (10004, 10020, 10021) and attempt < retries:
                last = OrderRejected(data["retcode"], data.get("comment", ""))
                time.sleep(0.25)
                if request.get("action") == TRADE_ACTION_DEAL and "type" in request:
                    tick = self.tick(request["symbol"])
                    request["price"] = tick.ask if request["type"] == ORDER_TYPE_BUY else tick.bid
                continue
            raise OrderRejected(data["retcode"], data.get("comment", ""))
        raise last or MT5Error("order failed after retries")

    def market_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        sl=None,
        tp=None,
        deviation=None,
        comment: str = "",
    ) -> dict:
        """Buy or sell at market. Sent immediately; validated first."""
        side = side.lower()
        if side not in ("buy", "sell"):
            raise MT5Error(f"side must be buy or sell, got {side!r}")
        info = self.symbol(symbol)
        self.check_symbol_allowed(info.name)
        volume = self.normalize_volume(info, volume)
        tick = self.tick(info.name)
        price = tick.ask if side == "buy" else tick.bid
        self.check_stops(info, side, price, sl, tp)
        request = {
            "action": TRADE_ACTION_DEAL,
            "symbol": info.name,
            "volume": volume,
            "type": ORDER_TYPE_BUY if side == "buy" else ORDER_TYPE_SELL,
            "price": price,
            "deviation": deviation if deviation is not None else self.config.default_deviation,
            "magic": self.config.magic,
            "comment": comment[:31],
            "type_time": ORDER_TIME_GTC,
            "type_filling": self.filling_mode(info),
        }
        if sl is not None:
            request["sl"] = sl
        if tp is not None:
            request["tp"] = tp
        return self._send(request)

    def pending_order(
        self, symbol, side, kind, volume, price, sl=None, tp=None, comment: str = ""
    ) -> dict:
        """Place a limit or stop order at a price."""
        side, kind = side.lower(), kind.lower()
        if (side, kind) not in PENDING_TYPES:
            raise MT5Error("pending order must be buy/sell combined with limit/stop")
        info = self.symbol(symbol)
        self.check_symbol_allowed(info.name)
        volume = self.normalize_volume(info, volume)
        tick = self.tick(info.name)
        market = tick.ask if side == "buy" else tick.bid
        if kind == "limit" and side == "buy" and price >= market:
            raise MT5Error(f"buy limit {price} must be below the market {market}")
        if kind == "limit" and side == "sell" and price <= market:
            raise MT5Error(f"sell limit {price} must be above the market {market}")
        if kind == "stop" and side == "buy" and price <= market:
            raise MT5Error(f"buy stop {price} must be above the market {market}")
        if kind == "stop" and side == "sell" and price >= market:
            raise MT5Error(f"sell stop {price} must be below the market {market}")
        self.check_stops(info, side, price, sl, tp)
        request = {
            "action": TRADE_ACTION_PENDING,
            "symbol": info.name,
            "volume": volume,
            "type": PENDING_TYPES[(side, kind)],
            "price": price,
            "magic": self.config.magic,
            "comment": comment[:31],
            "type_time": ORDER_TIME_GTC,
            "type_filling": self.filling_mode(info),
        }
        if sl is not None:
            request["sl"] = sl
        if tp is not None:
            request["tp"] = tp
        return self._send(request)

    # -- positions ---------------------------------------------------------
    def positions(self, symbol=None) -> list:
        raw = (
            self.mt5.positions_get(symbol=self.resolve_symbol(symbol))
            if symbol
            else self.mt5.positions_get()
        )
        return [as_dict(p) for p in (raw or [])]

    def position(self, ticket: int) -> dict:
        raw = self.mt5.positions_get(ticket=ticket)
        if not raw:
            raise MT5Error(f"no open position with ticket {ticket}")
        return as_dict(raw[0])

    def orders(self) -> list:
        return [as_dict(o) for o in (self.mt5.orders_get() or [])]

    def set_sltp(self, ticket: int, sl=None, tp=None) -> dict:
        """Attach or move stop-loss / take-profit on an open position."""
        pos = self.position(ticket)
        info = self.symbol(pos["symbol"])
        side = "buy" if pos["type"] == ORDER_TYPE_BUY else "sell"
        self.check_stops(info, side, pos["price_current"], sl, tp)
        request = {
            "action": TRADE_ACTION_SLTP,
            "symbol": pos["symbol"],
            "position": ticket,
            "sl": sl if sl is not None else pos.get("sl", 0.0),
            "tp": tp if tp is not None else pos.get("tp", 0.0),
            "magic": self.config.magic,
        }
        return self._send(request)

    def close_position(self, ticket: int, volume=None) -> dict:
        """Close a position, fully or partially, at market."""
        pos = self.position(ticket)
        info = self.symbol(pos["symbol"])
        closing_side = "sell" if pos["type"] == ORDER_TYPE_BUY else "buy"
        tick = self.tick(info.name)
        amount = pos["volume"] if volume is None else self.normalize_volume(info, volume)
        if amount > pos["volume"]:
            raise MT5Error(
                f"cannot close {amount} lots - position {ticket} holds {pos['volume']}"
            )
        request = {
            "action": TRADE_ACTION_DEAL,
            "symbol": info.name,
            "volume": amount,
            "type": ORDER_TYPE_SELL if closing_side == "sell" else ORDER_TYPE_BUY,
            "position": ticket,
            "price": tick.bid if closing_side == "sell" else tick.ask,
            "deviation": self.config.default_deviation,
            "magic": self.config.magic,
            "comment": "close",
            "type_time": ORDER_TIME_GTC,
            "type_filling": self.filling_mode(info),
        }
        return self._send(request)

    def cancel_order(self, ticket: int) -> dict:
        return self._send({"action": TRADE_ACTION_REMOVE, "order": ticket})

    def close_all(self, symbol=None) -> list:
        return [self.close_position(p["ticket"]) for p in self.positions(symbol)]

    # -- history and bars --------------------------------------------------
    def bars(self, symbol: str, timeframe: str, count: int = 500):
        resolved = self.resolve_symbol(symbol)
        tf = TIMEFRAMES.get(timeframe.upper())
        if tf is None:
            raise MT5Error(f"unknown timeframe {timeframe!r}; use {', '.join(TIMEFRAMES)}")
        rates = self.mt5.copy_rates_from_pos(resolved, tf, 0, count)
        if rates is None or len(rates) == 0:
            raise MT5Error(f"no bars returned for {resolved} {timeframe}")
        return rates

    def deals(self, days: int = 30) -> list:
        from datetime import datetime, timedelta

        now = datetime.now()
        raw = self.mt5.history_deals_get(now - timedelta(days=days), now)
        return [as_dict(d) for d in (raw or [])]
