"""Position sizing and stop placement.

One rule, applied without exception: the loss taken when the stop is hit
is a fixed fraction of current equity. Lot size is DERIVED from that, it is
never an input. A fixed lot size and a fixed risk percentage are mutually
exclusive; this module implements the second.
"""
from __future__ import annotations

from dataclasses import dataclass

from .instruments import Instrument


@dataclass(frozen=True)
class RiskConfig:
    risk_pct: float = 0.01          # fraction of equity risked per trade
    atr_stop_mult: float = 2.0      # stop distance = mult * ATR
    reward_risk: float = 2.0        # take-profit distance = RRR * stop distance
    max_lots: float = 100.0         # hard cap, safety valve
    max_concurrent: int = 1         # positions open at once


def stop_distance(atr_value: float, cfg: RiskConfig) -> float:
    """Stop distance in PRICE units."""
    return float(atr_value) * cfg.atr_stop_mult


def position_lots(
    equity: float,
    stop_dist_price: float,
    inst: Instrument,
    cfg: RiskConfig,
    usd_per_quote: float = 1.0,
) -> float:
    """Lots such that stop-out costs exactly risk_pct of equity.

    risk_cash = lots * contract_size * stop_dist_price * usd_per_quote
    """
    if stop_dist_price <= 0 or equity <= 0:
        return 0.0
    risk_cash = equity * cfg.risk_pct
    value_per_lot = inst.contract_size * stop_dist_price * usd_per_quote
    if value_per_lot <= 0:
        return 0.0
    lots = risk_cash / value_per_lot
    return inst.round_lot(min(lots, cfg.max_lots))
