"""Position sizing and portfolio risk. Pure functions - no terminal needed."""

from __future__ import annotations

from dataclasses import dataclass


class RiskError(Exception):
    pass


@dataclass
class Sizing:
    lots: float
    risk_amount: float
    stop_distance: float
    loss_at_stop: float
    lots_unrounded: float
    capped_by: str | None = None

    def as_rows(self, currency: str = "") -> list:
        rows = [
            ["Lots", f"{self.lots:.2f}"],
            ["Risk budget", f"{self.risk_amount:,.2f} {currency}".strip()],
            ["Stop distance", f"{self.stop_distance:.5f}"],
            ["Loss if stopped", f"{self.loss_at_stop:,.2f} {currency}".strip()],
        ]
        if self.capped_by:
            rows.append(["Capped by", self.capped_by])
        return rows


def value_per_lot(tick_value: float, tick_size: float) -> float:
    """Account currency gained per lot for one unit of price movement."""
    if tick_size <= 0:
        raise RiskError("tick_size must be positive")
    return tick_value / tick_size


def size_position(
    balance: float,
    risk_pct: float,
    entry: float,
    stop: float,
    tick_value: float,
    tick_size: float,
    volume_step: float = 0.01,
    volume_min: float = 0.01,
    volume_max: float = 100.0,
    max_volume: float | None = None,
) -> Sizing:
    """Lots such that being stopped out costs `risk_pct` of balance.

    Rounds *down* to the lot step - overshooting the risk budget by rounding up
    is the wrong direction to be wrong in.
    """
    if balance <= 0:
        raise RiskError("balance must be positive")
    if not 0 < risk_pct <= 100:
        raise RiskError("risk_pct must be between 0 and 100")
    distance = abs(entry - stop)
    if distance == 0:
        raise RiskError("entry and stop are the same price - no risk to size against")

    risk_amount = balance * risk_pct / 100
    per_lot = value_per_lot(tick_value, tick_size)
    raw = risk_amount / (distance * per_lot)

    lots = (int(raw / volume_step)) * volume_step
    lots = round(lots, 8)
    capped = None
    if lots > volume_max:
        lots, capped = volume_max, f"symbol volume_max {volume_max}"
    if max_volume and lots > max_volume:
        lots, capped = max_volume, f"config max_volume {max_volume}"
    if lots < volume_min:
        raise RiskError(
            f"risking {risk_pct}% of {balance:,.2f} over a {distance:.5f} stop needs "
            f"{raw:.4f} lots, below the {volume_min} minimum. Widen the stop, "
            f"raise the risk, or skip the trade."
        )
    return Sizing(
        lots=lots,
        risk_amount=risk_amount,
        stop_distance=distance,
        loss_at_stop=lots * distance * per_lot,
        lots_unrounded=raw,
        capped_by=capped,
    )


def r_multiple(entry: float, stop: float, exit_price: float, side: str) -> float:
    """How many multiples of the initial risk the trade returned."""
    risk = abs(entry - stop)
    if risk == 0:
        raise RiskError("no initial risk - entry equals stop")
    move = exit_price - entry if side.lower() == "buy" else entry - exit_price
    return move / risk


def open_risk(positions: list, per_lot_lookup) -> float:
    """Currency at risk across open positions that carry a stop.

    `per_lot_lookup(symbol)` returns value-per-lot-per-price-unit. Positions
    with no stop-loss are unbounded risk and are reported separately.
    """
    total = 0.0
    for pos in positions:
        sl = pos.get("sl") or 0
        if not sl:
            continue
        distance = abs(pos["price_open"] - sl)
        total += distance * pos["volume"] * per_lot_lookup(pos["symbol"])
    return total


def portfolio_heat(positions: list, equity: float, per_lot_lookup) -> dict:
    """Open risk as a percentage of equity, plus what is unprotected."""
    if equity <= 0:
        raise RiskError("equity must be positive")
    risked = open_risk(positions, per_lot_lookup)
    naked = [p for p in positions if not (p.get("sl") or 0)]
    return {
        "open_positions": len(positions),
        "risk_amount": risked,
        "heat_pct": risked / equity * 100,
        "without_stop": len(naked),
        "without_stop_symbols": sorted({p["symbol"] for p in naked}),
    }
