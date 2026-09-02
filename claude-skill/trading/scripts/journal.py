"""Trade journal: append-only JSONL, synced from MT5 deal history."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime

DEFAULT_PATH = os.path.expanduser("~/.local/share/mt5-trading/journal.jsonl")

DEAL_ENTRY_IN = 0
DEAL_ENTRY_OUT = 1


class JournalError(Exception):
    pass


def path(explicit: str | None = None) -> str:
    return os.path.expanduser(explicit or os.environ.get("MT5_JOURNAL", DEFAULT_PATH))


def load(explicit: str | None = None) -> list:
    file = path(explicit)
    if not os.path.exists(file):
        return []
    trades = []
    with open(file, encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                trades.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise JournalError(f"{file}:{line_number} is not valid JSON: {exc}") from exc
    return trades


def save(trades: list, explicit: str | None = None) -> str:
    file = path(explicit)
    os.makedirs(os.path.dirname(file), exist_ok=True)
    with open(file, "w", encoding="utf-8") as handle:
        for trade in trades:
            handle.write(json.dumps(trade, sort_keys=True) + "\n")
    return file


def trades_from_deals(deals: list) -> list:
    """Fold MT5 deals into round-trip trades keyed by position_id.

    MT5 records an entry deal and one or more exit deals per position; partial
    closes produce several exits, so profit and volume are summed.
    """
    grouped = defaultdict(list)
    for deal in deals:
        pid = deal.get("position_id")
        if pid:
            grouped[pid].append(deal)

    trades = []
    for pid, group in grouped.items():
        group.sort(key=lambda d: d.get("time", 0))
        entries = [d for d in group if d.get("entry") == DEAL_ENTRY_IN]
        exits = [d for d in group if d.get("entry") == DEAL_ENTRY_OUT]
        if not entries or not exits:
            continue  # still open, or history window cut it in half
        first, last = entries[0], exits[-1]
        volume = sum(d.get("volume", 0) for d in entries)
        profit = sum(d.get("profit", 0) for d in group)
        commission = sum(d.get("commission", 0) for d in group)
        swap = sum(d.get("swap", 0) for d in group)
        trades.append(
            {
                "position_id": pid,
                "symbol": first.get("symbol"),
                "side": "buy" if first.get("type") == 0 else "sell",
                "volume": round(volume, 4),
                "entry_price": first.get("price"),
                "exit_price": last.get("price"),
                "opened_at": datetime.utcfromtimestamp(first.get("time", 0)).isoformat() + "Z",
                "closed_at": datetime.utcfromtimestamp(last.get("time", 0)).isoformat() + "Z",
                "duration_min": round((last.get("time", 0) - first.get("time", 0)) / 60, 1),
                "profit": round(profit, 2),
                "commission": round(commission, 2),
                "swap": round(swap, 2),
                "net": round(profit + commission + swap, 2),
                "partial_exits": len(exits),
            }
        )
    return sorted(trades, key=lambda t: t["closed_at"])


def merge(existing: list, incoming: list) -> list:
    """Incoming MT5 facts win; locally added fields (notes, tags, R) survive."""
    by_id = {t["position_id"]: dict(t) for t in existing}
    for trade in incoming:
        current = by_id.get(trade["position_id"], {})
        local = {k: v for k, v in current.items() if k in ("note", "tags", "setup", "planned_r")}
        by_id[trade["position_id"]] = {**trade, **local}
    return sorted(by_id.values(), key=lambda t: t["closed_at"])


def annotate(trades: list, position_id: int, **fields) -> list:
    for trade in trades:
        if trade["position_id"] == position_id:
            trade.update({k: v for k, v in fields.items() if v is not None})
            return trades
    raise JournalError(f"no journalled trade with position_id {position_id}")


def max_drawdown(equity: list) -> float:
    """Largest peak-to-trough decline of a cumulative P&L curve."""
    peak, worst = 0.0, 0.0
    for value in equity:
        peak = max(peak, value)
        worst = min(worst, value - peak)
    return abs(worst)


def stats(trades: list) -> dict:
    """Win rate, expectancy, profit factor, drawdown - on net P&L."""
    closed = [t for t in trades if t.get("net") is not None]
    if not closed:
        return {"trades": 0}
    wins = [t for t in closed if t["net"] > 0]
    losses = [t for t in closed if t["net"] < 0]
    gross_win = sum(t["net"] for t in wins)
    gross_loss = abs(sum(t["net"] for t in losses))
    net = sum(t["net"] for t in closed)
    equity, running = [], 0.0
    for trade in closed:
        running += trade["net"]
        equity.append(running)
    avg_win = gross_win / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    win_rate = len(wins) / len(closed)
    rs = [t["r"] for t in closed if isinstance(t.get("r"), (int, float))]
    return {
        "trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "net": net,
        "gross_win": gross_win,
        "gross_loss": gross_loss,
        "profit_factor": (gross_win / gross_loss) if gross_loss else float("inf"),
        "expectancy": net / len(closed),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff": (avg_win / avg_loss) if avg_loss else float("inf"),
        "largest_win": max((t["net"] for t in closed), default=0.0),
        "largest_loss": min((t["net"] for t in closed), default=0.0),
        "max_drawdown": max_drawdown(equity),
        "avg_r": (sum(rs) / len(rs)) if rs else None,
        "commission": sum(t.get("commission", 0) for t in closed),
        "swap": sum(t.get("swap", 0) for t in closed),
    }


def by_symbol(trades: list) -> dict:
    grouped = defaultdict(list)
    for trade in trades:
        grouped[trade["symbol"]].append(trade)
    return {symbol: stats(group) for symbol, group in sorted(grouped.items())}
