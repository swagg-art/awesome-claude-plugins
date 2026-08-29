"""MetaTrader 5 execution layer.

Corrections against the common template this replaces:

1. `mt5.order_send_async()` DOES NOT EXIST in the MetaTrader5 Python
   package. OrderSendAsync() is an MQL5 language function; the Python
   binding exposes only the synchronous `order_send()`. Calling the async
   name raises AttributeError, so an "async" script never places a trade
   at all. Speed is not the constraint anyway - the terminal round-trip
   dominates, and on a strategy holding positions for hours it is noise.

2. `if result[0]:` is a success test that reports success on failure.
   result[0] is `retcode`, an integer. Every REJECTION is also a nonzero
   integer - 10004 requote, 10006 rejected, 10019 no money, 10030
   unsupported filling mode. Only 10009 (TRADE_RETCODE_DONE) means the
   order filled. The original check treats all of them as success.

3. Filling mode cannot be hardcoded. Brokers advertise which of FOK / IOC
   / RETURN they accept per symbol via symbol_info().filling_mode, and a
   mismatch returns 10030. This negotiates it.

4. Volume must be normalised to the symbol's volume_min / volume_max /
   volume_step before sending, or the order is rejected for a reason that
   looks like a connection problem.

Additionally: this module refuses to touch a live account unless
explicitly unlocked, and defaults to dry_run.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("tbot.live")

TRADE_RETCODE_DONE = 10009
TRADE_RETCODE_PLACED = 10008

RETCODE_MEANING = {
    10004: "requote", 10006: "request rejected", 10007: "cancelled by trader",
    10008: "order placed", 10009: "request completed", 10010: "partial fill",
    10011: "request processing error", 10012: "request timed out",
    10013: "invalid request", 10014: "invalid volume", 10015: "invalid price",
    10016: "invalid stops", 10017: "trading disabled", 10018: "market closed",
    10019: "insufficient funds", 10020: "prices changed",
    10021: "no quotes to process request", 10026: "autotrading disabled by server",
    10027: "autotrading disabled by client terminal",
    10030: "unsupported filling mode", 10031: "no connection to trade server",
}


class BrokerError(RuntimeError):
    pass


@dataclass
class OrderResult:
    ok: bool
    retcode: int
    meaning: str
    order: int | None = None
    deal: int | None = None
    price: float | None = None
    volume: float | None = None
    comment: str = ""
    dry_run: bool = False
    raw: Any = None

    def __str__(self) -> str:
        tag = "DRY-RUN" if self.dry_run else ("FILLED" if self.ok else "REJECTED")
        return (f"[{tag}] retcode={self.retcode} ({self.meaning}) "
                f"vol={self.volume} px={self.price} order={self.order}")


@dataclass
class MT5Broker:
    """Thin, defensive wrapper around the MetaTrader5 Python package.

    mt5 is injected so this is testable without a Windows terminal.
    """
    mt5: Any = None
    dry_run: bool = True
    allow_live: bool = False
    magic: int = 100200
    deviation_points: int = 10
    connected: bool = False
    _account: Any = field(default=None, repr=False)

    def __post_init__(self):
        if self.mt5 is None:
            try:
                import MetaTrader5 as _mt5
                self.mt5 = _mt5
            except ImportError as e:
                raise BrokerError(
                    "MetaTrader5 package not available. It is Windows-only and "
                    "requires a running MT5 terminal. Install with "
                    "`pip install MetaTrader5` on the Windows/VPS host."
                ) from e

    # ---------------- connection ----------------

    def connect(self, *, login: int | None = None, password: str | None = None,
                server: str | None = None, path: str | None = None) -> None:
        kwargs = {k: v for k, v in
                  dict(login=login, password=password, server=server, path=path).items()
                  if v is not None}
        if not self.mt5.initialize(**kwargs):
            raise BrokerError(f"MT5 initialize failed: {self.mt5.last_error()}")

        term = self.mt5.terminal_info()
        if term is None:
            raise BrokerError("terminal_info() returned None after initialize")
        if not getattr(term, "trade_allowed", False):
            raise BrokerError(
                "Algo trading is disabled in the terminal. Enable it: "
                "Tools > Options > Expert Advisors > Allow algorithmic trading.")

        acct = self.mt5.account_info()
        if acct is None:
            raise BrokerError(f"account_info() returned None: {self.mt5.last_error()}")
        self._account = acct
        self.connected = True

        is_demo = getattr(acct, "trade_mode", None) == getattr(
            self.mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
        if not is_demo and not self.allow_live:
            self.disconnect()
            raise BrokerError(
                f"Account {acct.login} is NOT a demo account. Refusing to connect. "
                "Pass allow_live=True only when you have deliberately decided to "
                "trade real money with a strategy that has passed out-of-sample "
                "testing.")

        log.info("connected: login=%s server=%s demo=%s balance=%.2f %s "
                 "dry_run=%s", acct.login, acct.server, is_demo, acct.balance,
                 acct.currency, self.dry_run)

    def disconnect(self) -> None:
        try:
            self.mt5.shutdown()
        finally:
            self.connected = False

    def account(self):
        acct = self.mt5.account_info()
        if acct is None:
            raise BrokerError(f"account_info() failed: {self.mt5.last_error()}")
        self._account = acct
        return acct

    def open_positions(self, symbol: str | None = None) -> int:
        pos = (self.mt5.positions_get(symbol=symbol) if symbol
               else self.mt5.positions_get())
        return 0 if pos is None else len(pos)

    # ---------------- symbol plumbing ----------------

    def _symbol(self, symbol: str):
        info = self.mt5.symbol_info(symbol)
        if info is None:
            raise BrokerError(f"symbol {symbol!r} not found on this server")
        if not info.visible and not self.mt5.symbol_select(symbol, True):
            raise BrokerError(f"could not select symbol {symbol!r} in Market Watch")
        return self.mt5.symbol_info(symbol) or info

    def normalize_volume(self, symbol: str, lots: float) -> float:
        """Clamp and round to the symbol's own volume grid."""
        info = self._symbol(symbol)
        vmin = getattr(info, "volume_min", 0.01)
        vmax = getattr(info, "volume_max", 100.0)
        step = getattr(info, "volume_step", 0.01) or 0.01
        if lots < vmin:
            return 0.0
        lots = min(lots, vmax)
        steps = round(lots / step)
        out = round(steps * step, 8)
        if out < vmin:
            return 0.0
        # rounding must never push size UP past the risk budget
        if out > lots:
            out = round((steps - 1) * step, 8)
        return out if out >= vmin else 0.0

    def pick_filling_mode(self, symbol: str) -> int:
        """Choose a filling mode the broker actually accepts for this symbol."""
        info = self._symbol(symbol)
        mask = getattr(info, "filling_mode", 0)
        FOK = getattr(self.mt5, "ORDER_FILLING_FOK", 0)
        IOC = getattr(self.mt5, "ORDER_FILLING_IOC", 1)
        RET = getattr(self.mt5, "ORDER_FILLING_RETURN", 2)
        SYMBOL_FILLING_FOK = 1
        SYMBOL_FILLING_IOC = 2
        if mask & SYMBOL_FILLING_IOC:
            return IOC
        if mask & SYMBOL_FILLING_FOK:
            return FOK
        return RET

    # ---------------- orders ----------------

    def place_market_order(self, symbol: str, side: str, lots: float, *,
                           sl_price: float | None = None,
                           tp_price: float | None = None,
                           comment: str = "tbot") -> OrderResult:
        """Send a market order. Synchronous - order_send_async does not exist."""
        if not self.connected:
            raise BrokerError("not connected - call connect() first")

        side_u = side.upper()
        if side_u not in ("BUY", "SELL"):
            raise BrokerError(f"side must be BUY or SELL, got {side!r}")

        info = self._symbol(symbol)
        if getattr(info, "trade_mode", 4) == getattr(
                self.mt5, "SYMBOL_TRADE_MODE_DISABLED", 0):
            raise BrokerError(f"trading disabled for {symbol}")

        vol = self.normalize_volume(symbol, lots)
        if vol <= 0:
            raise BrokerError(
                f"volume {lots} rounds below the minimum "
                f"({getattr(info,'volume_min',0.01)}) for {symbol}")

        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            raise BrokerError(f"no tick for {symbol}: {self.mt5.last_error()}")

        is_buy = side_u == "BUY"
        price = tick.ask if is_buy else tick.bid
        if not price:
            raise BrokerError(f"{symbol} tick has no {'ask' if is_buy else 'bid'}")

        # Stops must sit the right side of price, or you get retcode 10016.
        if sl_price is not None:
            if is_buy and sl_price >= price:
                raise BrokerError(f"BUY stop {sl_price} must be below price {price}")
            if not is_buy and sl_price <= price:
                raise BrokerError(f"SELL stop {sl_price} must be above price {price}")
        if tp_price is not None:
            if is_buy and tp_price <= price:
                raise BrokerError(f"BUY target {tp_price} must be above price {price}")
            if not is_buy and tp_price >= price:
                raise BrokerError(f"SELL target {tp_price} must be below price {price}")

        digits = getattr(info, "digits", 5)
        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(vol),
            "type": self.mt5.ORDER_TYPE_BUY if is_buy else self.mt5.ORDER_TYPE_SELL,
            "price": round(price, digits),
            "deviation": self.deviation_points,
            "magic": self.magic,
            "comment": comment[:31],
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.pick_filling_mode(symbol),
        }
        if sl_price is not None:
            request["sl"] = round(sl_price, digits)
        if tp_price is not None:
            request["tp"] = round(tp_price, digits)

        if self.dry_run:
            log.info("DRY-RUN order not sent: %s", request)
            return OrderResult(ok=True, retcode=0, meaning="dry run - not sent",
                               volume=vol, price=price, dry_run=True, raw=request)

        # order_check first: catches margin and stop errors without touching
        # the market. Cheap, and it turns a rejection into a readable message.
        chk = self.mt5.order_check(request)
        if chk is not None and chk.retcode not in (0, TRADE_RETCODE_DONE):
            return OrderResult(
                ok=False, retcode=chk.retcode,
                meaning=RETCODE_MEANING.get(chk.retcode, "pre-trade check failed"),
                volume=vol, price=price, comment=getattr(chk, "comment", ""), raw=chk)

        result = self.mt5.order_send(request)
        if result is None:
            raise BrokerError(f"order_send returned None: {self.mt5.last_error()}")

        rc = int(result.retcode)
        ok = rc in (TRADE_RETCODE_DONE, TRADE_RETCODE_PLACED)
        out = OrderResult(
            ok=ok, retcode=rc, meaning=RETCODE_MEANING.get(rc, f"unmapped retcode {rc}"),
            order=getattr(result, "order", None), deal=getattr(result, "deal", None),
            price=getattr(result, "price", price), volume=getattr(result, "volume", vol),
            comment=getattr(result, "comment", ""), raw=result)
        (log.info if ok else log.error)("%s %s %s", symbol, side_u, out)
        return out

    def close_all(self, symbol: str | None = None) -> list[OrderResult]:
        """Flatten. Used by the kill switch."""
        positions = (self.mt5.positions_get(symbol=symbol) if symbol
                     else self.mt5.positions_get()) or []
        results = []
        for p in positions:
            if getattr(p, "magic", None) not in (None, self.magic):
                continue  # never touch positions this bot did not open
            side = "SELL" if p.type == self.mt5.ORDER_TYPE_BUY else "BUY"
            results.append(self.place_market_order(
                p.symbol, side, p.volume, comment="tbot close"))
        return results
