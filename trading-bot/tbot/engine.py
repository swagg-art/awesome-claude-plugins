"""Event-driven backtest engine.

Execution model, chosen to be pessimistic wherever ambiguity exists:

  * A signal is computed from bar t's CLOSE and filled at bar t+1's OPEN.
    Never same-bar. Same-bar fills are the second-most-common way a retail
    backtest invents profit that does not exist.
  * Entry and exit both cross the spread and both take adverse slippage.
  * If a bar's range contains BOTH the stop and the take-profit, the stop
    is assumed to have been hit first. Intrabar order is unknowable from
    OHLC; assuming the good outcome is how you fool yourself.
  * Gaps through the stop fill at the open, not at the stop level.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import costs as cost_mod
from .instruments import Instrument
from .risk import RiskConfig, position_lots, stop_distance


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp | None
    side: int                # +1 long, -1 short
    lots: float
    entry_price: float
    exit_price: float | None
    stop: float
    target: float
    pnl: float = 0.0
    costs: float = 0.0          # all-in: spread + slippage + commission + funding
    spread_cost: float = 0.0    # the one retail backtests hide inside fill prices
    commission_cost: float = 0.0
    funding_cost: float = 0.0
    bars_held: int = 0
    exit_reason: str = ""


@dataclass
class BacktestResult:
    equity: pd.Series
    trades: list[Trade] = field(default_factory=list)
    config: dict = field(default_factory=dict)

    def trades_frame(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([t.__dict__ for t in self.trades])


def run_backtest(
    bars: pd.DataFrame,
    signal: pd.Series,
    atr_series: pd.Series,
    inst: Instrument,
    cfg: RiskConfig,
    initial_equity: float = 10_000.0,
    slippage_pips: float = 0.5,
    bars_per_day: float = 24.0,
    quote_rate: pd.Series | None = None,
) -> BacktestResult:
    """Run the loop.

    bars   : DataFrame with open/high/low/close, DatetimeIndex, ascending.
    signal : +1 / -1 / 0 per bar, computed from that bar's close.
    atr_series : ATR aligned to bars, used for stop distance at entry.
    """
    required = {"open", "high", "low", "close"}
    if not required.issubset(bars.columns):
        raise ValueError(f"bars needs columns {required}, got {set(bars.columns)}")
    if not bars.index.is_monotonic_increasing:
        raise ValueError("bars index must be sorted ascending")

    idx = bars.index
    o = bars["open"].to_numpy(float)
    h = bars["high"].to_numpy(float)
    l = bars["low"].to_numpy(float)
    sig = signal.reindex(idx).fillna(0).to_numpy(float)
    atr_v = atr_series.reindex(idx).to_numpy(float)

    # Account-currency value of one unit of the quote currency, per bar.
    # USD-quoted pairs: 1.0. JPY-quoted (USDJPY): 1/price, since P&L accrues
    # in yen. Getting this wrong misprices every trade by the FX rate itself.
    if quote_rate is None:
        qr = np.ones(len(idx))
    else:
        qr = quote_rate.reindex(idx).ffill().to_numpy(float)

    equity = initial_equity
    equity_curve = np.full(len(idx), np.nan)
    trades: list[Trade] = []

    pos = None  # dict of open position state

    for i in range(len(idx) - 1):
        equity_curve[i] = equity

        # ---- manage an open position on bar i -------------------------
        if pos is not None:
            hit_stop = l[i] <= pos["stop"] if pos["side"] > 0 else h[i] >= pos["stop"]
            hit_tgt = h[i] >= pos["target"] if pos["side"] > 0 else l[i] <= pos["target"]

            exit_px = None
            reason = ""
            if hit_stop:
                # gap-through fills at the open, else at the stop level
                gapped = (o[i] < pos["stop"]) if pos["side"] > 0 else (o[i] > pos["stop"])
                exit_px = o[i] if gapped else pos["stop"]
                reason = "stop"
            elif hit_tgt:
                gapped = (o[i] > pos["target"]) if pos["side"] > 0 else (o[i] < pos["target"])
                exit_px = o[i] if gapped else pos["target"]
                reason = "target"

            if exit_px is not None:
                fill = cost_mod.fill_price(exit_px, -pos["side"], inst, slippage_pips)
                gross = ((fill - pos["entry"]) * pos["side"] * pos["lots"]
                         * inst.contract_size * qr[i])
                days = pos["bars"] / bars_per_day
                comm = cost_mod.commission(pos["lots"], inst)
                fund = cost_mod.funding(pos["lots"], pos["entry"], inst, days)
                # spread + slippage, round trip, in account currency. This is
                # already reflected in `gross` via the fill prices; we compute
                # it here so the report can SHOW it instead of hiding it.
                per_side = (cost_mod.spread_cost_price(inst)
                            + slippage_pips * inst.pip_size)
                exec_cost = 2.0 * per_side * pos["lots"] * inst.contract_size * qr[i]
                c = comm + fund
                equity += gross - c
                trades.append(Trade(
                    entry_time=pos["t0"], exit_time=idx[i], side=pos["side"],
                    lots=pos["lots"], entry_price=pos["entry"], exit_price=fill,
                    stop=pos["stop"], target=pos["target"],
                    pnl=gross - c,
                    costs=comm + fund + exec_cost,
                    spread_cost=exec_cost, commission_cost=comm, funding_cost=fund,
                    bars_held=pos["bars"], exit_reason=reason,
                ))
                pos = None
            else:
                pos["bars"] += 1

        # ---- consider a new entry, filled on bar i+1 open -------------
        if pos is None and sig[i] != 0 and np.isfinite(atr_v[i]) and atr_v[i] > 0:
            side = int(np.sign(sig[i]))
            sd = stop_distance(atr_v[i], cfg)
            lots = position_lots(equity, sd, inst, cfg, usd_per_quote=qr[i])
            if lots > 0:
                entry = cost_mod.fill_price(o[i + 1], side, inst, slippage_pips)
                entry_c = cost_mod.commission(lots, inst)
                equity -= entry_c
                pos = {
                    "t0": idx[i + 1], "side": side, "lots": lots, "entry": entry,
                    "stop": entry - side * sd,
                    "target": entry + side * sd * cfg.reward_risk,
                    "bars": 0, "entry_cost": entry_c,
                }

    equity_curve[-1] = equity
    return BacktestResult(
        equity=pd.Series(equity_curve, index=idx, name="equity"),
        trades=trades,
        config={
            "instrument": inst.symbol, "risk_pct": cfg.risk_pct,
            "atr_stop_mult": cfg.atr_stop_mult, "reward_risk": cfg.reward_risk,
            "slippage_pips": slippage_pips, "spread_pips": inst.typical_spread_pips,
            "initial_equity": initial_equity,
        },
    )
