"""Transaction costs. Applied on every fill, without exception."""
from __future__ import annotations

from .instruments import Instrument


def spread_cost_price(inst: Instrument) -> float:
    """Half-spread in price units, paid on entry AND on exit."""
    return (inst.typical_spread_pips * inst.pip_size) / 2.0


def apply_slippage(price: float, side: int, inst: Instrument, slippage_pips: float) -> float:
    """Adverse fill. side=+1 buy, -1 sell. Always moves against you."""
    return price + side * slippage_pips * inst.pip_size


def fill_price(mid: float, side: int, inst: Instrument, slippage_pips: float = 0.0) -> float:
    """Executable price: cross the spread, then take slippage, both adverse."""
    half = spread_cost_price(inst)
    return apply_slippage(mid + side * half, side, inst, slippage_pips)


def commission(lots: float, inst: Instrument) -> float:
    return abs(lots) * inst.commission_per_lot


def funding(lots: float, price: float, inst: Instrument, days: float) -> float:
    """Overnight carry. Charged as a cost regardless of direction (conservative)."""
    if inst.funding_rate_daily == 0.0 or days <= 0:
        return 0.0
    notional = abs(lots) * inst.contract_size * price
    return notional * inst.funding_rate_daily * days
