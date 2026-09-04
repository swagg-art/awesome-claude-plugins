"""The real backend: the MetaTrader 5 Python package talking to a terminal.

The `MetaTrader5` package is a thin wrapper over the terminal's own IPC and
only ships wheels for Windows. It is imported inside `connect()` rather than at
module scope so that importing Native MT5 on macOS or Linux — for tests, for
the mock adapter, for reading the code — never fails.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .base import (
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

_RETCODE_DONE = 10009


class TerminalAdapter:
    """Implements the Adapter protocol against a running MT5 terminal."""

    name = "terminal"

    def __init__(self, config):
        self._config = config
        self._mt5 = None

    # -- lifecycle ---------------------------------------------------------

    def connect(self) -> None:
        try:
            import MetaTrader5 as mt5  # noqa: N813 — the package's own casing
        except ImportError as exc:  # pragma: no cover — platform dependent
            raise AdapterError(
                "the MetaTrader5 package is not installed. It ships wheels for "
                "Windows only; on macOS or Linux run the terminal under Wine or "
                "point Native MT5 at a Windows host. Falling back: set "
                "NATIVE_MT5_ADAPTER=mock to explore the tools without a broker."
            ) from exc

        creds = self._config.credentials
        kwargs = {}
        if creds.terminal_path:
            kwargs["path"] = creds.terminal_path
        if creds.is_complete:
            kwargs.update(
                login=creds.login, password=creds.password, server=creds.server
            )

        if not mt5.initialize(**kwargs):
            code, message = mt5.last_error()
            raise AdapterError(f"could not attach to the MT5 terminal ({code}): {message}")

        self._mt5 = mt5

    def close(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()
            self._mt5 = None

    @property
    def _api(self):
        if self._mt5 is None:
            raise AdapterError("adapter is not connected — call connect() first")
        return self._mt5

    def _fail(self, what: str) -> AdapterError:
        code, message = self._api.last_error()
        return AdapterError(f"{what} failed ({code}): {message}")

    # -- account -----------------------------------------------------------

    def account(self) -> Account:
        info = self._api.account_info()
        if info is None:
            raise self._fail("account_info")
        return Account(
            login=info.login,
            name=info.name,
            server=info.server,
            currency=info.currency,
            balance=round(info.balance, 2),
            equity=round(info.equity, 2),
            margin=round(info.margin, 2),
            margin_free=round(info.margin_free, 2),
            margin_level=round(info.margin_level, 2),
            leverage=info.leverage,
            profit=round(info.profit, 2),
        )

    # -- instruments -------------------------------------------------------

    def symbols(self, search: str = "") -> list[SymbolInfo]:
        group = f"*{search.strip().upper()}*" if search else None
        raw = self._api.symbols_get(group) if group else self._api.symbols_get()
        if raw is None:
            raise self._fail("symbols_get")
        return [self._to_symbol(s) for s in raw]

    def symbol(self, name: str) -> SymbolInfo:
        key = (name or "").strip().upper()
        info = self._api.symbol_info(key)
        if info is None:
            raise AdapterError(
                f"symbol {key} is not available. It may need enabling in the "
                "terminal's Market Watch, or the broker may name it differently "
                "(EURUSD.m, EURUSD_i, …) — try list_symbols with a search term."
            )
        if not info.visible and not self._api.symbol_select(key, True):
            raise self._fail(f"symbol_select({key})")
        return self._to_symbol(info)

    @staticmethod
    def _to_symbol(info) -> SymbolInfo:
        return SymbolInfo(
            name=info.name,
            description=info.description,
            digits=info.digits,
            point=info.point,
            tick_size=info.trade_tick_size or info.point,
            tick_value=info.trade_tick_value,
            contract_size=info.trade_contract_size,
            volume_min=info.volume_min,
            volume_max=info.volume_max,
            volume_step=info.volume_step,
            currency_profit=info.currency_profit,
        )

    # -- prices ------------------------------------------------------------

    def quote(self, symbol: str) -> Quote:
        info = self.symbol(symbol)
        tick = self._api.symbol_info_tick(info.name)
        if tick is None:
            raise self._fail(f"symbol_info_tick({info.name})")
        return Quote(
            symbol=info.name,
            time=datetime.fromtimestamp(tick.time, tz=UTC).isoformat(),
            bid=tick.bid,
            ask=tick.ask,
        )

    def candles(self, symbol: str, timeframe: str, count: int = 100) -> list[Candle]:
        info = self.symbol(symbol)
        tf = normalise_timeframe(timeframe)
        mt5_tf = getattr(self._api, f"TIMEFRAME_{tf}")
        rates = self._api.copy_rates_from_pos(info.name, mt5_tf, 0, count)
        if rates is None or len(rates) == 0:
            raise self._fail(f"copy_rates_from_pos({info.name}, {tf})")
        return [
            Candle(
                time=datetime.fromtimestamp(int(r["time"]), tz=UTC).isoformat(),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                tick_volume=int(r["tick_volume"]),
            )
            for r in rates
        ]

    # -- positions and history --------------------------------------------

    def positions(self, symbol: str = "") -> list[Position]:
        key = (symbol or "").strip().upper()
        raw = self._api.positions_get(symbol=key) if key else self._api.positions_get()
        if raw is None:
            return []
        return [
            Position(
                ticket=p.ticket,
                symbol=p.symbol,
                side="buy" if p.type == self._api.POSITION_TYPE_BUY else "sell",
                volume=p.volume,
                open_price=p.price_open,
                current_price=p.price_current,
                stop_loss=p.sl or None,
                take_profit=p.tp or None,
                profit=round(p.profit, 2),
                opened_at=datetime.fromtimestamp(p.time, tz=UTC).isoformat(),
                comment=p.comment,
            )
            for p in raw
        ]

    def history(self, days: int = 30) -> list[Deal]:
        now = datetime.now(UTC)
        raw = self._api.history_deals_get(now - timedelta(days=days), now)
        if raw is None:
            return []
        return [
            Deal(
                ticket=d.ticket,
                symbol=d.symbol,
                side="buy" if d.type == self._api.DEAL_TYPE_BUY else "sell",
                volume=d.volume,
                price=d.price,
                profit=round(d.profit, 2),
                commission=round(d.commission, 2),
                swap=round(d.swap, 2),
                time=datetime.fromtimestamp(d.time, tz=UTC).isoformat(),
            )
            for d in raw
            if d.symbol
        ]

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
        mt5 = self._api
        info = self.symbol(symbol)
        tick = mt5.symbol_info_tick(info.name)
        if tick is None:
            raise self._fail(f"symbol_info_tick({info.name})")

        is_buy = side == "buy"
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": info.name,
            "volume": float(volume),
            "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
            "price": tick.ask if is_buy else tick.bid,
            "deviation": self._config.deviation_points,
            "magic": self._config.magic,
            "comment": (comment or "native-mt5")[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        if stop_loss is not None:
            request["sl"] = float(stop_loss)
        if take_profit is not None:
            request["tp"] = float(take_profit)

        return self._send(request, f"{side} {volume} {info.name}")

    def close_position(self, ticket: int) -> OrderResult:
        mt5 = self._api
        found = mt5.positions_get(ticket=ticket)
        if not found:
            raise AdapterError(f"no open position with ticket {ticket}")
        position = found[0]
        tick = mt5.symbol_info_tick(position.symbol)
        if tick is None:
            raise self._fail(f"symbol_info_tick({position.symbol})")

        is_buy = position.type == mt5.POSITION_TYPE_BUY
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
            "price": tick.bid if is_buy else tick.ask,
            "deviation": self._config.deviation_points,
            "magic": self._config.magic,
            "comment": "native-mt5 close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        return self._send(request, f"close {ticket}")

    def _send(self, request: dict, description: str) -> OrderResult:
        result = self._api.order_send(request)
        if result is None:
            raise self._fail(f"order_send({description})")
        if result.retcode != _RETCODE_DONE:
            return OrderResult(
                ok=False,
                ticket=None,
                price=None,
                volume=None,
                message=(
                    f"broker rejected {description}: "
                    f"retcode {result.retcode} — {result.comment}"
                ),
            )
        return OrderResult(
            ok=True,
            ticket=result.order or None,
            price=result.price,
            volume=result.volume,
            message=f"{description} executed at {result.price}",
        )
