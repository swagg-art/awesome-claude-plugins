#!/usr/bin/env python3
"""Walk-forward backtest of the signals.py rules.

At each bar close the engine sees only the last --window bars (default 50,
the same history the live skill uses), exactly as it would in real time.

Trade model (no look-ahead):
  * Signal at bar t close -> enter at bar t+1 open, stop/targets from the
    ATR known at bar t, re-anchored to the actual fill price.
  * Exit on stop or target, checked on each later bar's high/low. If both are
    touched in the same bar the stop is assumed first (conservative).
  * Optional exit when the bias flips away from the trade (--exit-on-flip).
    Off by default: the live skill only defines stop and target exits.
  * One position at a time. Costs are a round-trip % of price (--cost-pct).

Results are in R (multiples of the initial risk), so instruments with very
different prices compare directly.

Usage:
  backtest.py data/BTCUSD.csv [more.csv ...] [--target tp1|tp2] [--cost-pct 0.1]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import signals  # noqa: E402

RISK_PCT = 1.0  # equity risked per trade for the compounded return figure


def backtest(
    bars: list[dict],
    window: int = 50,
    target: str = "tp2",
    cost_pct: float = 0.1,
    exit_on_flip: bool = False,
    long_only: bool = False,
) -> dict:
    bars = sorted(bars, key=lambda b: b["t"])
    trades: list[dict] = []
    pos = None
    mult = {"tp1": 1.5, "tp2": 3.0}[target]

    for i in range(window - 1, len(bars)):
        bar = bars[i]
        if pos:
            stop_hit = bar["l"] <= pos["stop"] if pos["side"] > 0 else bar["h"] >= pos["stop"]
            tgt_hit = bar["h"] >= pos["target"] if pos["side"] > 0 else bar["l"] <= pos["target"]
            exit_px = reason = None
            if stop_hit:
                # a gap through the stop fills at the open, not the stop
                gap = bar["o"] < pos["stop"] if pos["side"] > 0 else bar["o"] > pos["stop"]
                exit_px, reason = (bar["o"] if gap else pos["stop"]), "stop"
            elif tgt_hit:
                exit_px, reason = pos["target"], "target"
            if exit_px is not None:
                trades.append(_close(pos, exit_px, bar["t"], reason, cost_pct))
                pos = None

        if i == len(bars) - 1:
            break  # no next bar to act on
        sig = signals.analyse("BT", bars[i - window + 1 : i + 1])
        side = {"LONG": 1, "SHORT": -1}.get(sig["bias"], 0)
        if long_only and side < 0:
            side = 0

        if pos and exit_on_flip and side != pos["side"]:
            trades.append(_close(pos, bars[i + 1]["o"], bars[i + 1]["t"], "flip", cost_pct))
            pos = None

        if not pos and side:
            entry = bars[i + 1]["o"]
            risk = 1.5 * sig["atr14"]
            pos = {
                "side": side,
                "entry": entry,
                "t_in": bars[i + 1]["t"],
                "risk": risk,
                "stop": entry - side * risk,
                "target": entry + side * mult * sig["atr14"],
                "score": sig["score"],
            }

    if pos:  # mark open trade to the last close
        trades.append(_close(pos, bars[-1]["c"], bars[-1]["t"], "open", cost_pct))

    first = bars[window - 1]["c"]
    return {
        "bars": len(bars),
        "from": bars[0]["t"],
        "to": bars[-1]["t"],
        "buy_hold_pct": round((bars[-1]["c"] / first - 1) * 100, 2),
        **stats(trades),
        "trades": trades,
    }


def resample(bars: list[dict], tf: str) -> list[dict]:
    """Aggregate bars into a higher timeframe: 2h, 4h, 8h, 1d, 1w or 1mo."""
    from datetime import datetime

    def key(t: str):
        d = datetime.fromisoformat(t[:19])
        if tf.endswith("h"):
            return (d.date(), d.hour // int(tf[:-1]))
        if tf == "1d":
            return d.date()
        if tf == "1w":
            return d.isocalendar()[:2]
        if tf == "1mo":
            return (d.year, d.month)
        raise ValueError(f"unknown timeframe {tf}")

    out: list[dict] = []
    last = None
    for b in sorted(bars, key=lambda b: b["t"]):
        k = key(b["t"])
        if k != last:
            out.append(dict(b))
            last = k
        else:
            cur = out[-1]
            cur["h"], cur["l"], cur["c"] = max(cur["h"], b["h"]), min(cur["l"], b["l"]), b["c"]
    return out


def _close(pos: dict, px: float, t: str, reason: str, cost_pct: float) -> dict:
    gross = pos["side"] * (px - pos["entry"])
    cost = pos["entry"] * cost_pct / 100
    return {
        "side": "LONG" if pos["side"] > 0 else "SHORT",
        "t_in": pos["t_in"],
        "t_out": t,
        "entry": pos["entry"],
        "exit": px,
        "reason": reason,
        "r": round((gross - cost) / pos["risk"], 3),
        "pct": round((gross - cost) / pos["entry"] * 100, 3),
    }


def stats(trades: list[dict]) -> dict:
    rs = [t["r"] for t in trades]
    if not rs:
        return {"n": 0, "longs": 0, "shorts": 0, "win_rate": 0, "avg_win_r": 0, "avg_loss_r": 0,
                "expectancy_r": 0, "total_r": 0, "profit_factor": None, "max_dd_r": 0,
                "return_1pct_risk": 0, "equity_r": []}
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    equity = peak = max_dd = 0.0
    curve = []
    for r in rs:
        equity += r
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
        curve.append(round(equity, 3))
    compounded = 1.0  # fixed-fractional: risk RISK_PCT of equity on every trade
    for r in rs:
        compounded *= 1 + RISK_PCT / 100 * r
    return {
        "n": len(rs),
        "longs": sum(t["side"] == "LONG" for t in trades),
        "shorts": sum(t["side"] == "SHORT" for t in trades),
        "win_rate": round(len(wins) / len(rs) * 100, 1),
        "avg_win_r": round(sum(wins) / len(wins), 3) if wins else 0,
        "avg_loss_r": round(sum(losses) / len(losses), 3) if losses else 0,
        "expectancy_r": round(sum(rs) / len(rs), 3),
        "total_r": round(sum(rs), 2),
        "profit_factor": round(sum(wins) / -sum(losses), 2) if losses and sum(losses) < 0 else None,
        "max_dd_r": round(max_dd, 2),
        "return_1pct_risk": round((compounded - 1) * 100, 2),
        "equity_r": curve,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--window", type=int, default=50)
    p.add_argument("--target", choices=["tp1", "tp2"], default="tp2")
    p.add_argument("--cost-pct", type=float, default=0.1, help="round-trip cost as %% of price")
    p.add_argument("--exit-on-flip", action="store_true", help="also exit when the bias changes")
    p.add_argument("--long-only", action="store_true", help="ignore SHORT signals")
    p.add_argument("--resample", help="aggregate input to 2h, 4h, 8h, 1d, 1w or 1mo first")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    out = {}
    for f in args.files:
        for sym, bars in signals.load(f).items():
            if args.resample:
                bars, sym = resample(bars, args.resample), f"{sym}@{args.resample}"
            out[sym] = backtest(bars, args.window, args.target, args.cost_pct, args.exit_on_flip, args.long_only)

    if args.json:
        json.dump(out, sys.stdout, indent=1)
        print()
        return 0
    print("| Symbol | Period | Trades | Win % | Avg win R | Avg loss R | Expectancy R | Total R | PF | Max DD R | Return % @1% risk | Buy&hold % |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for sym, r in out.items():
        if not r["n"]:
            print(f"| {sym} | {r['from'][:10]} – {r['to'][:10]} | 0 | - | - | - | - | - | - | - | - | {r['buy_hold_pct']} |")
            continue
        print(
            f"| {sym} | {r['from'][:10]} – {r['to'][:10]} | {r['n']} | {r['win_rate']} | {r['avg_win_r']} | "
            f"{r['avg_loss_r']} | {r['expectancy_r']:+} | {r['total_r']:+} | {r['profit_factor']} | "
            f"{r['max_dd_r']} | {r['return_1pct_risk']} | {r['buy_hold_pct']} |"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
