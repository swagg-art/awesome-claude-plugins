"""Performance metrics. Reported with their limitations attached."""
from __future__ import annotations

import numpy as np
import pandas as pd


def max_drawdown(equity: pd.Series) -> tuple[float, pd.Timestamp | None]:
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min()), (dd.idxmin() if len(dd) else None)


def summarise(equity: pd.Series, trades: pd.DataFrame, periods_per_year: float = 252 * 24) -> dict:
    eq = equity.dropna()
    if len(eq) < 2:
        return {"error": "not enough equity points"}

    rets = eq.pct_change().dropna()
    total_return = float(eq.iloc[-1] / eq.iloc[0] - 1.0)
    years = len(eq) / periods_per_year
    cagr = float((eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1.0) if years > 0 else np.nan

    sd = rets.std()
    sharpe = float(rets.mean() / sd * np.sqrt(periods_per_year)) if sd and sd > 0 else np.nan
    downside = rets[rets < 0].std()
    sortino = float(rets.mean() / downside * np.sqrt(periods_per_year)) if downside and downside > 0 else np.nan

    mdd, mdd_at = max_drawdown(eq)

    out = {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": mdd,
        "max_drawdown_at": str(mdd_at) if mdd_at is not None else None,
        "calmar": float(cagr / abs(mdd)) if mdd and mdd < 0 and np.isfinite(cagr) else np.nan,
        "years": years,
    }

    if trades is None or trades.empty:
        out.update({"n_trades": 0, "note": "no trades taken - nothing to evaluate"})
        return out

    pnl = trades["pnl"]
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    gross_win, gross_loss = wins.sum(), abs(losses.sum())

    out.update({
        "n_trades": int(len(trades)),
        "win_rate": float(len(wins) / len(trades)),
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "profit_factor": float(gross_win / gross_loss) if gross_loss > 0 else np.inf,
        "expectancy": float(pnl.mean()),
        "total_costs": float(trades["costs"].sum()),
        "cost_drag_pct_of_gross": (
            float(trades["costs"].sum() / (abs(pnl).sum() + trades["costs"].sum()))
            if len(trades) else np.nan
        ),
        "avg_bars_held": float(trades["bars_held"].mean()),
        "exit_mix": trades["exit_reason"].value_counts().to_dict(),
    })
    return out


def format_report(m: dict) -> str:
    if m.get("n_trades", 0) == 0:
        return f"No trades taken. {m.get('note','')}"
    pct = lambda x: f"{x*100:6.2f}%"
    lines = [
        f"  trades           {m['n_trades']}",
        f"  total return     {pct(m['total_return'])}",
        f"  CAGR             {pct(m['cagr'])}",
        f"  Sharpe           {m['sharpe']:6.2f}",
        f"  Sortino          {m['sortino']:6.2f}",
        f"  max drawdown     {pct(m['max_drawdown'])}",
        f"  Calmar           {m['calmar']:6.2f}",
        f"  win rate         {pct(m['win_rate'])}",
        f"  profit factor    {m['profit_factor']:6.2f}",
        f"  expectancy/trade {m['expectancy']:8.2f}",
        f"  total costs      {m['total_costs']:8.2f}",
        f"  cost drag        {pct(m['cost_drag_pct_of_gross'])} of gross flow",
        f"  avg bars held    {m['avg_bars_held']:6.1f}",
        f"  exits            {m['exit_mix']}",
    ]
    return "\n".join(lines)
