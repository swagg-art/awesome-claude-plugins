"""The tool layer.

Every MCP tool is a thin wrapper over a method here. Keeping the logic in a
plain class means the whole surface is testable without the MCP runtime, and
that a future REST or CLI front end gets the same behaviour for free.

Methods return plain dicts, already rounded and labelled for a model to read.
"""

from __future__ import annotations

from .adapters import build_adapter
from .adapters.base import Adapter, AdapterError
from .config import Config
from .risk import size_position, summarise_deals
from .safety import Guard, OrderIntent, SafetyError, confirmation_token


class Session:
    """A configured, connected view of one trading account."""

    def __init__(self, config: Config | None = None, adapter: Adapter | None = None):
        self.config = config or Config.from_env()
        self._adapter = adapter or build_adapter(self.config)
        self._connected = False
        self.guard = Guard(
            mode=self.config.mode,
            max_order_volume=self.config.max_order_volume,
            max_open_positions=self.config.max_open_positions,
            symbol_allowlist=self.config.symbol_allowlist,
        )

    # -- lifecycle ---------------------------------------------------------

    def open(self) -> Session:
        if not self._connected:
            self._adapter.connect()
            self._connected = True
        return self

    def close(self) -> None:
        if self._connected:
            self._adapter.close()
            self._connected = False

    def __enter__(self) -> Session:
        return self.open()

    def __exit__(self, *_exc) -> None:
        self.close()

    # -- read-only tools ---------------------------------------------------

    def status(self) -> dict:
        """What this server is connected to and what it is allowed to do."""
        payload = {
            "connected": self._connected,
            "adapter": self._adapter.name,
            **self.config.describe(),
        }
        if self.config.mode.value == "readonly":
            payload["note"] = (
                "Read-only: market data and account inspection work, orders are "
                "refused. This is the default and has to be changed deliberately."
            )
        elif self.config.mode.value == "paper":
            payload["note"] = "Paper: orders are simulated and never reach a broker."
        else:
            payload["note"] = (
                "LIVE: orders reach the broker. Each one needs a confirmation "
                "token from preview_order."
            )
        return payload

    def account(self) -> dict:
        account = self._adapter.account()
        data = account.to_dict()
        data["drawdown_from_balance_pct"] = (
            round(100 * (account.balance - account.equity) / account.balance, 2)
            if account.balance
            else 0.0
        )
        return data

    def list_symbols(self, search: str = "", limit: int = 50) -> dict:
        found = self._adapter.symbols(search)
        return {
            "count": len(found),
            "shown": min(len(found), limit),
            "symbols": [s.to_dict() for s in found[:limit]],
        }

    def symbol_info(self, symbol: str) -> dict:
        return self._adapter.symbol(symbol).to_dict()

    def quote(self, symbol: str) -> dict:
        info = self._adapter.symbol(symbol)
        quote = self._adapter.quote(symbol)
        data = quote.to_dict()
        data["spread_points"] = round(quote.spread / info.point, 1)
        return data

    def candles(self, symbol: str, timeframe: str = "H1", count: int = 100) -> dict:
        bars = self._adapter.candles(symbol, timeframe, count)
        closes = [b.close for b in bars]
        return {
            "symbol": self._adapter.symbol(symbol).name,
            "timeframe": timeframe.upper(),
            "count": len(bars),
            "first_time": bars[0].time if bars else None,
            "last_time": bars[-1].time if bars else None,
            "highest": max((b.high for b in bars), default=None),
            "lowest": min((b.low for b in bars), default=None),
            "last_close": closes[-1] if closes else None,
            "candles": [b.to_dict() for b in bars],
        }

    def positions(self, symbol: str = "") -> dict:
        found = self._adapter.positions(symbol)
        return {
            "count": len(found),
            "floating_profit": round(sum(p.profit for p in found), 2),
            "total_volume": round(sum(p.volume for p in found), 2),
            "positions": [p.to_dict() for p in found],
        }

    def history(self, days: int = 30) -> dict:
        deals = self._adapter.history(days)
        return {
            "days": days,
            "count": len(deals),
            "deals": [d.to_dict() for d in deals],
        }

    def performance(self, days: int = 30) -> dict:
        deals = self._adapter.history(days)
        return {"days": days, **summarise_deals(deals)}

    # -- sizing ------------------------------------------------------------

    def size_position(
        self,
        symbol: str,
        side: str,
        entry: float,
        stop_loss: float,
        risk_pct: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """Lot size for a given stop, capped by the configured risk ceiling."""

        info = self._adapter.symbol(symbol)
        account = self._adapter.account()
        requested = self.config.max_risk_per_trade_pct if risk_pct is None else risk_pct

        capped_risk = min(requested, self.config.max_risk_per_trade_pct)
        sized = size_position(
            symbol=info,
            side=side,
            entry=entry,
            stop_loss=stop_loss,
            balance=account.balance,
            risk_pct=capped_risk,
            take_profit=take_profit,
            max_volume=self.config.max_order_volume,
        )
        data = sized.to_dict()
        data["balance"] = account.balance
        if capped_risk < requested:
            data["risk_pct_note"] = (
                f"requested {requested}% was clamped to the server's "
                f"{self.config.max_risk_per_trade_pct}% ceiling"
            )
        return data

    # -- write tools -------------------------------------------------------

    def preview_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """Dry-run an order: what it would cost, and the token to execute it.

        Always safe to call — it never reaches the broker, in any mode.
        """

        intent = OrderIntent(symbol, side, volume, stop_loss, take_profit).normalised()
        info = self._adapter.symbol(intent.symbol)
        quote = self._adapter.quote(intent.symbol)
        entry = quote.ask if intent.side == "buy" else quote.bid
        open_positions = len(self._adapter.positions())

        preview: dict = {
            "symbol": info.name,
            "side": intent.side,
            "volume": intent.volume,
            "estimated_entry": entry,
            "stop_loss": intent.stop_loss,
            "take_profit": intent.take_profit,
            "spread_cost": round(
                quote.spread / info.tick_size * info.tick_value * intent.volume, 2
            ),
            "open_positions": open_positions,
            "mode": self.config.mode.value,
        }

        if intent.stop_loss is not None:
            from .risk import loss_per_lot

            per_lot = loss_per_lot(info, entry, intent.stop_loss)
            preview["risk_at_stop"] = round(per_lot * intent.volume, 2)
            balance = self._adapter.account().balance
            preview["risk_pct_of_balance"] = (
                round(100 * per_lot * intent.volume / balance, 2) if balance else None
            )
        else:
            preview["risk_at_stop"] = None
            preview["warning"] = "no stop_loss — this order has unbounded downside"

        try:
            self.guard.check(
                intent,
                open_positions=open_positions,
                token=confirmation_token(intent),
            )
            preview["would_be_accepted"] = True
            preview["blocked_by"] = None
        except SafetyError as exc:
            preview["would_be_accepted"] = False
            preview["blocked_by"] = str(exc)

        if self.config.mode.requires_confirmation:
            preview["confirmation_token"] = confirmation_token(intent)
            preview["next_step"] = (
                "Show this preview to the human. Only if they approve, call "
                "place_order with the same arguments plus this confirmation_token."
            )
        return preview

    def place_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "",
        confirm_token: str | None = None,
    ) -> dict:
        intent = OrderIntent(
            symbol, side, volume, stop_loss, take_profit, comment
        ).normalised()
        self.guard.check(
            intent,
            open_positions=len(self._adapter.positions()),
            token=confirm_token,
        )
        result = self._adapter.place_order(
            intent.symbol,
            intent.side,
            intent.volume,
            intent.stop_loss,
            intent.take_profit,
            intent.comment,
        )
        return result.to_dict()

    def close_position(self, ticket: int) -> dict:
        if not self.config.mode.allows_orders:
            raise SafetyError(
                "server is in readonly mode — nothing was closed. Restart with "
                "NATIVE_MT5_MODE=paper or live to manage positions."
            )
        return self._adapter.close_position(int(ticket)).to_dict()


__all__ = ["Session", "SafetyError", "AdapterError"]
