"""Position sizing and trade arithmetic.

Kept free of any broker dependency so it can be unit tested directly and
reused by a backtester later. Everything here works off the contract spec the
adapter already returns.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .adapters.base import SymbolInfo


class RiskError(ValueError):
    """The inputs describe a trade that cannot be sized."""


@dataclass(frozen=True)
class PositionSize:
    symbol: str
    side: str
    entry: float
    stop_loss: float
    volume: float
    risk_amount: float
    risk_pct: float
    stop_distance_points: float
    loss_at_stop: float
    reward_at_target: float | None
    reward_risk_ratio: float | None
    capped_by: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def round_to_step(volume: float, step: float) -> float:
    """Round a lot size *down* to the broker's volume step.

    Down, not nearest: rounding up would silently exceed the risk the caller
    asked for.
    """

    if step <= 0:
        raise RiskError(f"volume_step must be positive, got {step}")
    steps = math.floor(round(volume / step, 9))
    return round(steps * step, 8)


def loss_per_lot(symbol: SymbolInfo, entry: float, stop_loss: float) -> float:
    """Account-currency loss from one lot if the stop is hit."""

    if symbol.tick_size <= 0:
        raise RiskError(f"{symbol.name} reports a non-positive tick_size")
    if symbol.tick_value <= 0:
        raise RiskError(f"{symbol.name} reports a non-positive tick_value")
    distance = abs(entry - stop_loss)
    if distance <= 0:
        raise RiskError("entry and stop_loss cannot be equal — the stop has no distance")
    return (distance / symbol.tick_size) * symbol.tick_value


def size_position(
    *,
    symbol: SymbolInfo,
    side: str,
    entry: float,
    stop_loss: float,
    balance: float,
    risk_pct: float,
    take_profit: float | None = None,
    max_volume: float | None = None,
) -> PositionSize:
    """Size a trade so that hitting the stop costs `risk_pct` of `balance`."""

    side = side.strip().lower()
    if side not in {"buy", "sell"}:
        raise RiskError(f"side must be 'buy' or 'sell', got {side!r}")
    if balance <= 0:
        raise RiskError(f"balance must be positive, got {balance}")
    if risk_pct <= 0 or risk_pct > 100:
        raise RiskError(f"risk_pct must be in (0, 100], got {risk_pct}")
    if side == "buy" and stop_loss >= entry:
        raise RiskError("a buy stop_loss must sit below the entry price")
    if side == "sell" and stop_loss <= entry:
        raise RiskError("a sell stop_loss must sit above the entry price")

    risk_amount = balance * (risk_pct / 100.0)
    per_lot = loss_per_lot(symbol, entry, stop_loss)
    raw_volume = risk_amount / per_lot

    capped_by: str | None = None
    volume = raw_volume
    if max_volume is not None and volume > max_volume:
        volume, capped_by = max_volume, "max_order_volume"
    if volume > symbol.volume_max:
        volume, capped_by = symbol.volume_max, "symbol volume_max"

    volume = round_to_step(volume, symbol.volume_step)

    if volume < symbol.volume_min:
        raise RiskError(
            f"risking {risk_pct}% of {balance:.2f} sizes to {raw_volume:.4f} lots, "
            f"below {symbol.name}'s minimum of {symbol.volume_min}. "
            "Widen the risk, tighten the stop, or trade a smaller contract."
        )

    loss_at_stop = volume * per_lot
    reward = None
    ratio = None
    if take_profit is not None:
        if side == "buy" and take_profit <= entry:
            raise RiskError("a buy take_profit must sit above the entry price")
        if side == "sell" and take_profit >= entry:
            raise RiskError("a sell take_profit must sit below the entry price")
        reward = volume * loss_per_lot(symbol, entry, take_profit)
        ratio = round(reward / loss_at_stop, 3) if loss_at_stop else None

    return PositionSize(
        symbol=symbol.name,
        side=side,
        entry=entry,
        stop_loss=stop_loss,
        volume=volume,
        risk_amount=round(risk_amount, 2),
        risk_pct=risk_pct,
        stop_distance_points=round(abs(entry - stop_loss) / symbol.point, 1),
        loss_at_stop=round(loss_at_stop, 2),
        reward_at_target=round(reward, 2) if reward is not None else None,
        reward_risk_ratio=ratio,
        capped_by=capped_by,
    )


def summarise_deals(deals) -> dict:
    """Headline performance stats over a list of closed deals."""

    closed = [d for d in deals if d.profit or d.commission or d.swap]
    if not closed:
        return {
            "trades": 0,
            "net_profit": 0.0,
            "win_rate_pct": None,
            "profit_factor": None,
            "average_win": None,
            "average_loss": None,
            "largest_win": None,
            "largest_loss": None,
        }

    nets = [d.profit + d.commission + d.swap for d in closed]
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n < 0]
    gross_loss = abs(sum(losses))

    return {
        "trades": len(closed),
        "net_profit": round(sum(nets), 2),
        "win_rate_pct": round(100 * len(wins) / len(closed), 1),
        "profit_factor": round(sum(wins) / gross_loss, 3) if gross_loss else None,
        "average_win": round(sum(wins) / len(wins), 2) if wins else None,
        "average_loss": round(sum(losses) / len(losses), 2) if losses else None,
        "largest_win": round(max(wins), 2) if wins else None,
        "largest_loss": round(min(losses), 2) if losses else None,
    }
