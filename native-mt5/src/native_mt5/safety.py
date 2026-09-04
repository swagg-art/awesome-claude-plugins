"""The guard rails that sit between the model and a real trading account.

The rule this module enforces is simple: reading is always allowed, writing
never happens by accident. A write needs the server to be started in a mode
that permits it, the order to survive every configured cap, and — in live
mode — the caller to echo back a confirmation token that only a human who
read the preview could have.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum


class TradeMode(StrEnum):
    """How much damage this server is allowed to do."""

    READONLY = "readonly"
    """Market data and account inspection only. The default."""

    PAPER = "paper"
    """Orders are simulated inside the adapter; nothing reaches a broker."""

    LIVE = "live"
    """Orders reach the broker. Requires a confirmation token per order."""

    @classmethod
    def parse(cls, raw: str) -> TradeMode:
        value = (raw or "").strip().lower()
        for mode in cls:
            if mode.value == value:
                return mode
        allowed = ", ".join(m.value for m in cls)
        raise ValueError(f"unknown trade mode {raw!r}; expected one of: {allowed}")

    @property
    def allows_orders(self) -> bool:
        return self is not TradeMode.READONLY

    @property
    def requires_confirmation(self) -> bool:
        return self is TradeMode.LIVE


class SafetyError(RuntimeError):
    """An order was refused before it could reach the adapter."""


@dataclass(frozen=True)
class OrderIntent:
    """A normalised order request, independent of any broker API."""

    symbol: str
    side: str  # "buy" | "sell"
    volume: float
    stop_loss: float | None = None
    take_profit: float | None = None
    comment: str = ""

    def normalised(self) -> OrderIntent:
        return OrderIntent(
            symbol=self.symbol.strip().upper(),
            side=self.side.strip().lower(),
            volume=float(self.volume),
            stop_loss=self.stop_loss,
            take_profit=self.take_profit,
            comment=self.comment,
        )


def confirmation_token(intent: OrderIntent) -> str:
    """A short token derived from the order itself.

    Deterministic on purpose: the preview call and the execute call produce the
    same token for the same order, so a changed volume or symbol invalidates a
    token the caller is holding.
    """

    intent = intent.normalised()
    payload = "|".join(
        [
            intent.symbol,
            intent.side,
            f"{intent.volume:.4f}",
            f"{intent.stop_loss:.6f}" if intent.stop_loss is not None else "-",
            f"{intent.take_profit:.6f}" if intent.take_profit is not None else "-",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class Guard:
    """Evaluates an order against the limits the operator configured."""

    mode: TradeMode
    max_order_volume: float
    max_open_positions: int
    symbol_allowlist: tuple[str, ...] = ()

    def check(
        self,
        intent: OrderIntent,
        *,
        open_positions: int,
        token: str | None = None,
    ) -> None:
        """Raise SafetyError unless every rule passes."""

        intent = intent.normalised()

        if not self.mode.allows_orders:
            raise SafetyError(
                "server is in readonly mode — no order was placed. "
                "Restart with NATIVE_MT5_MODE=paper or live to enable trading."
            )

        if intent.side not in {"buy", "sell"}:
            raise SafetyError(f"side must be 'buy' or 'sell', got {intent.side!r}")

        if intent.volume <= 0:
            raise SafetyError(f"volume must be positive, got {intent.volume}")

        if intent.volume > self.max_order_volume:
            raise SafetyError(
                f"volume {intent.volume} exceeds the configured cap of "
                f"{self.max_order_volume} lots"
            )

        if self.symbol_allowlist and intent.symbol not in self.symbol_allowlist:
            allowed = ", ".join(self.symbol_allowlist)
            raise SafetyError(f"symbol {intent.symbol} is not in the allowlist: {allowed}")

        if open_positions >= self.max_open_positions:
            raise SafetyError(
                f"already holding {open_positions} positions, at the configured "
                f"cap of {self.max_open_positions}"
            )

        self._check_stops(intent)

        if self.mode.requires_confirmation:
            expected = confirmation_token(intent)
            if token != expected:
                raise SafetyError(
                    "live order requires a confirmation token. Call preview_order "
                    "first, show the preview to the human, then pass the token it "
                    "returned."
                )

    @staticmethod
    def _check_stops(intent: OrderIntent) -> None:
        sl, tp = intent.stop_loss, intent.take_profit
        if sl is not None and sl <= 0:
            raise SafetyError(f"stop_loss must be a positive price, got {sl}")
        if tp is not None and tp <= 0:
            raise SafetyError(f"take_profit must be a positive price, got {tp}")
        if sl is None or tp is None:
            return
        if intent.side == "buy" and not sl < tp:
            raise SafetyError("for a buy, stop_loss must sit below take_profit")
        if intent.side == "sell" and not sl > tp:
            raise SafetyError("for a sell, stop_loss must sit above take_profit")
