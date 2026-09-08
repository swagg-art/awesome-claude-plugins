"""Turn RSI signals into round-trip trades with explicit exit rules.

``rsi_signals`` answers "when is momentum interesting?". It says nothing about
when to get out. This module closes that gap: it consumes a signal stream and
walks it bar by bar into completed trades, applying whichever exit conditions
you enable.

Three exit families, freely combinable - whichever fires first wins:

1. **Opposite signal** - flat (or reversed) when a contrary signal fills.
   Simple, stays in trends, gives back a lot at turns.
2. **RSI level** - close when RSI reaches a level (50 to bank the mean
   reversion, 70 to ride it further). The classic partner to a band entry.
3. **Risk based** - ATR stop, ATR target, ATR trailing stop, and/or a time
   stop. Needs highs/lows to be meaningful; degrades to close-to-close
   ranges without them.

Fills and lookahead
-------------------
A signal computed from bar *n*'s close cannot be traded at bar *n*'s close.
Every fill is therefore delayed by ``entry_delay_bars`` (default 1) and priced
at that bar's close, the most conservative thing available from close-only
data. Stops and targets fill at their level only when highs/lows are supplied;
otherwise they fill at the close of the bar that breached them. When a bar
breaches both stop and target, the stop is assumed first.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

try:  # package import
    from .rsi_signals import BUY, SELL, RsiConfig, Signal, generate_signals, load_csv, rsi
except ImportError:  # direct script execution
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from rsi.rsi_signals import (  # type: ignore[no-redef]
        BUY,
        SELL,
        RsiConfig,
        Signal,
        generate_signals,
        load_csv,
        rsi,
    )

__all__ = [
    "Trade",
    "ExitPolicy",
    "atr",
    "simulate",
    "summarize_trades",
]

LONG = "LONG"
SHORT = "SHORT"


# --------------------------------------------------------------------------- #
# True range
# --------------------------------------------------------------------------- #
def atr(
    closes: Sequence[float],
    highs: Optional[Sequence[float]] = None,
    lows: Optional[Sequence[float]] = None,
    period: int = 14,
) -> List[Optional[float]]:
    """Average True Range (Wilder smoothing), aligned to ``closes``.

    With no highs/lows the true range collapses to ``|close - prev_close|``,
    which understates real range - fine for sizing stops consistently, wrong
    if you need absolute volatility.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    n = len(closes)
    hi = list(highs) if highs is not None else list(closes)
    lo = list(lows) if lows is not None else list(closes)
    if not (len(hi) == len(lo) == n):
        raise ValueError("highs/lows must be the same length as closes")

    out: List[Optional[float]] = [None] * n
    if n < 2:
        return out

    ranges = [hi[0] - lo[0]]
    for i in range(1, n):
        prev = closes[i - 1]
        ranges.append(max(hi[i] - lo[i], abs(hi[i] - prev), abs(lo[i] - prev)))

    if n <= period:
        return out
    value = sum(ranges[1 : period + 1]) / period
    out[period] = value
    for i in range(period + 1, n):
        value = (value * (period - 1) + ranges[i]) / period
        out[i] = value
    return out


# --------------------------------------------------------------------------- #
# Policy + trade
# --------------------------------------------------------------------------- #
@dataclass
class ExitPolicy:
    """Which exit conditions are armed. Unset conditions are simply not checked.

    Every enabled condition is evaluated on every bar; the first to trigger
    closes the position, in this order: stop, target, trailing stop, RSI level,
    time stop, opposite signal.
    """

    # 1. opposite signal
    on_opposite_signal: bool = True
    reverse_on_opposite: bool = False  # flip into the new direction, not flat

    # 2. RSI level (long exits at/above, short exits at/below)
    rsi_exit_long: Optional[float] = None
    rsi_exit_short: Optional[float] = None

    # 3. risk based, all measured in ATR multiples at entry
    atr_period: int = 14
    stop_atr: Optional[float] = None
    target_atr: Optional[float] = None
    trail_atr: Optional[float] = None
    time_stop_bars: Optional[int] = None

    # execution
    entry_delay_bars: int = 1
    allow_shorts: bool = True
    cost_bps: float = 0.0  # per side, in basis points; 10 = 0.10%
    require_atr_for_risk_exits: bool = True
    """Skip an entry when a risk exit is armed but ATR is unusable at the fill
    bar - during the ATR warm-up, or on a stretch so flat that ATR is zero.
    Taking the trade anyway would open a position with no stop attached."""

    def armed(self) -> List[str]:
        """Names of the conditions that can actually close a position."""
        names = []
        if self.stop_atr is not None:
            names.append("atr_stop")
        if self.target_atr is not None:
            names.append("atr_target")
        if self.trail_atr is not None:
            names.append("atr_trail")
        if self.rsi_exit_long is not None or self.rsi_exit_short is not None:
            names.append("rsi_level")
        if self.time_stop_bars is not None:
            names.append("time_stop")
        if self.on_opposite_signal:
            names.append("opposite_signal")
        return names

    # -- presets ------------------------------------------------------------ #
    @classmethod
    def opposite_signal(cls, reverse: bool = False, **kwargs) -> "ExitPolicy":
        """Hold until a contrary signal fills. Trend friendly, slow to turn."""
        return cls(on_opposite_signal=True, reverse_on_opposite=reverse, **kwargs)

    @classmethod
    def rsi_level(
        cls, long_exit: float = 50.0, short_exit: float = 50.0, **kwargs
    ) -> "ExitPolicy":
        """Bank the mean reversion at an RSI level. 50 is the neutral target;
        70/30 rides the move further at the cost of round trips."""
        return cls(
            rsi_exit_long=long_exit,
            rsi_exit_short=short_exit,
            on_opposite_signal=True,
            **kwargs,
        )

    @classmethod
    def risk(
        cls,
        stop_atr: float = 2.0,
        target_atr: Optional[float] = 3.0,
        trail_atr: Optional[float] = None,
        time_stop_bars: Optional[int] = None,
        **kwargs,
    ) -> "ExitPolicy":
        """Let risk decide the exit; RSI only picks the entry."""
        return cls(
            stop_atr=stop_atr,
            target_atr=target_atr,
            trail_atr=trail_atr,
            time_stop_bars=time_stop_bars,
            on_opposite_signal=True,
            **kwargs,
        )

    @classmethod
    def combined(cls, **kwargs) -> "ExitPolicy":
        """All three families at once: hard risk limits, an RSI take-profit,
        and a contrary signal as the backstop. Whichever comes first wins."""
        defaults = dict(
            stop_atr=2.0,
            target_atr=3.0,
            trail_atr=2.5,
            rsi_exit_long=65.0,
            rsi_exit_short=35.0,
            time_stop_bars=30,
            on_opposite_signal=True,
        )
        defaults.update(kwargs)
        return cls(**defaults)  # type: ignore[arg-type]


@dataclass(frozen=True)
class Trade:
    """One completed round trip."""

    direction: str  # LONG | SHORT
    entry_index: int
    entry_price: float
    exit_index: int
    exit_price: float
    entry_source: str  # which signal rule opened it
    exit_reason: str  # which condition closed it
    gross_return: float  # signed, in the trade's direction
    net_return: float  # after cost_bps on both sides
    bars_held: int
    mae: float  # worst excursion against the trade, as a fraction
    mfe: float  # best excursion in favour, as a fraction
    entry_timestamp: Optional[str] = None
    exit_timestamp: Optional[str] = None

    def as_dict(self) -> Dict[str, object]:
        return {
            "direction": self.direction,
            "entry_index": self.entry_index,
            "entry_timestamp": self.entry_timestamp,
            "entry_price": round(self.entry_price, 6),
            "entry_source": self.entry_source,
            "exit_index": self.exit_index,
            "exit_timestamp": self.exit_timestamp,
            "exit_price": round(self.exit_price, 6),
            "exit_reason": self.exit_reason,
            "bars_held": self.bars_held,
            "gross_return": round(self.gross_return, 5),
            "net_return": round(self.net_return, 5),
            "mae": round(self.mae, 5),
            "mfe": round(self.mfe, 5),
        }


@dataclass
class _Open:
    """Mutable state of the position currently on."""

    direction: str
    entry_index: int
    entry_price: float
    entry_source: str
    atr_at_entry: Optional[float]
    stop: Optional[float] = None
    target: Optional[float] = None
    trail: Optional[float] = None
    mae: float = 0.0
    mfe: float = 0.0


# --------------------------------------------------------------------------- #
# Simulation
# --------------------------------------------------------------------------- #
def simulate(
    closes: Sequence[float],
    signals: Sequence[Signal],
    policy: Optional[ExitPolicy] = None,
    highs: Optional[Sequence[float]] = None,
    lows: Optional[Sequence[float]] = None,
    rsi_values: Optional[Sequence[Optional[float]]] = None,
    rsi_period: int = 14,
    timestamps: Optional[Sequence[str]] = None,
) -> List[Trade]:
    """Walk the signals into completed trades. One position at a time, no pyramiding.

    A position still open when the data runs out is closed at the final bar
    with ``exit_reason="end_of_data"`` - it is not a real exit, and
    :func:`summarize_trades` reports how many trades ended that way.

    When a risk exit is armed but ATR is unusable at the fill bar, the entry is
    skipped rather than taken without a stop (see
    ``ExitPolicy.require_atr_for_risk_exits``).
    """
    pol = policy or ExitPolicy()
    n = len(closes)
    if n == 0:
        return []
    if pol.entry_delay_bars < 0:
        raise ValueError("entry_delay_bars must be >= 0")

    values = list(rsi_values) if rsi_values is not None else rsi(closes, rsi_period)
    needs_atr = any(
        x is not None for x in (pol.stop_atr, pol.target_atr, pol.trail_atr)
    )
    atr_values = atr(closes, highs, lows, pol.atr_period) if needs_atr else [None] * n

    hi = list(highs) if highs is not None else list(closes)
    lo = list(lows) if lows is not None else list(closes)
    has_ohlc = highs is not None and lows is not None

    fills = _fills_by_bar(signals, pol.entry_delay_bars, n)

    trades: List[Trade] = []
    open_pos: Optional[_Open] = None
    skipped_no_atr = 0

    def close_out(pos: _Open, index: int, price: float, reason: str) -> None:
        gross = (
            (price - pos.entry_price) / pos.entry_price
            if pos.direction == LONG
            else (pos.entry_price - price) / pos.entry_price
        )
        cost = 2.0 * pol.cost_bps / 10_000.0
        trades.append(
            Trade(
                direction=pos.direction,
                entry_index=pos.entry_index,
                entry_price=pos.entry_price,
                exit_index=index,
                exit_price=price,
                entry_source=pos.entry_source,
                exit_reason=reason,
                gross_return=gross,
                net_return=gross - cost,
                bars_held=index - pos.entry_index,
                mae=pos.mae,
                mfe=pos.mfe,
                entry_timestamp=timestamps[pos.entry_index] if timestamps else None,
                exit_timestamp=timestamps[index] if timestamps else None,
            )
        )

    for i in range(n):
        # --- 1. manage the open position, on bars after its entry ---------- #
        if open_pos is not None and i > open_pos.entry_index:
            pos = open_pos
            entry = pos.entry_price
            if pos.direction == LONG:
                pos.mae = min(pos.mae, (lo[i] - entry) / entry)
                pos.mfe = max(pos.mfe, (hi[i] - entry) / entry)
            else:
                pos.mae = min(pos.mae, (entry - hi[i]) / entry)
                pos.mfe = max(pos.mfe, (entry - lo[i]) / entry)

            if pos.trail is not None and pos.atr_at_entry is not None:
                distance = pol.trail_atr * (atr_values[i] or pos.atr_at_entry)  # type: ignore[operator]
                pos.trail = (
                    max(pos.trail, hi[i] - distance)
                    if pos.direction == LONG
                    else min(pos.trail, lo[i] + distance)
                )

            exit_at: Optional[Tuple[float, str]] = None
            long_side = pos.direction == LONG

            # stop before target: assume the worse fill when a bar spans both
            if pos.stop is not None and _breached(pos.stop, hi[i], lo[i], long_side, stop=True):
                exit_at = (pos.stop if has_ohlc else closes[i], "atr_stop")
            elif pos.trail is not None and _breached(pos.trail, hi[i], lo[i], long_side, stop=True):
                exit_at = (pos.trail if has_ohlc else closes[i], "atr_trail")
            elif pos.target is not None and _breached(
                pos.target, hi[i], lo[i], long_side, stop=False
            ):
                exit_at = (pos.target if has_ohlc else closes[i], "atr_target")
            else:
                level = pol.rsi_exit_long if long_side else pol.rsi_exit_short
                current = values[i]
                if (
                    level is not None
                    and current is not None
                    and ((long_side and current >= level) or (not long_side and current <= level))
                ):
                    exit_at = (closes[i], "rsi_level")
                elif (
                    pol.time_stop_bars is not None
                    and i - pos.entry_index >= pol.time_stop_bars
                ):
                    exit_at = (closes[i], "time_stop")

            if exit_at is not None:
                close_out(pos, i, exit_at[0], exit_at[1])
                open_pos = None

        # --- 2. process a signal filling on this bar ----------------------- #
        signal = fills.get(i)
        if signal is None:
            continue
        wants = LONG if signal.direction == BUY else SHORT

        if open_pos is not None:
            if open_pos.direction == wants:
                continue  # no pyramiding
            if not pol.on_opposite_signal:
                continue  # contrary signal ignored; other exits still apply
            close_out(open_pos, i, closes[i], "opposite_signal")
            open_pos = None
            if not pol.reverse_on_opposite:
                continue

        if wants == SHORT and not pol.allow_shorts:
            continue
        if needs_atr and pol.require_atr_for_risk_exits and not atr_values[i]:
            skipped_no_atr += 1  # no usable stop distance -> no trade
            continue
        open_pos = _enter(wants, i, closes[i], signal.source, atr_values[i], pol)

    if open_pos is not None:
        close_out(open_pos, n - 1, closes[n - 1], "end_of_data")

    return trades


def _enter(
    direction: str,
    index: int,
    price: float,
    source: str,
    atr_now: Optional[float],
    pol: ExitPolicy,
) -> _Open:
    pos = _Open(
        direction=direction,
        entry_index=index,
        entry_price=price,
        entry_source=source,
        atr_at_entry=atr_now,
    )
    if atr_now:
        sign = 1.0 if direction == LONG else -1.0
        if pol.stop_atr is not None:
            pos.stop = price - sign * pol.stop_atr * atr_now
        if pol.target_atr is not None:
            pos.target = price + sign * pol.target_atr * atr_now
        if pol.trail_atr is not None:
            pos.trail = price - sign * pol.trail_atr * atr_now
    return pos


def _breached(level: float, hi: float, lo: float, long_side: bool, stop: bool) -> bool:
    """Did this bar's range reach the level, in the direction that matters?"""
    if stop:
        return lo <= level if long_side else hi >= level
    return hi >= level if long_side else lo <= level


def _fills_by_bar(
    signals: Sequence[Signal], delay: int, n: int
) -> Dict[int, Signal]:
    """Map fill bar -> signal. Same-bar collisions resolve to the strongest."""
    fills: Dict[int, Signal] = {}
    for s in signals:
        bar = s.index + delay
        if bar >= n:
            continue  # no bar left to fill on
        current = fills.get(bar)
        if current is None or s.strength > current.strength:
            fills[bar] = s
    return fills


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def summarize_trades(trades: Sequence[Trade], use_net: bool = True) -> Dict[str, object]:
    """Per-trade statistics. Sequential, single position, compounded equity.

    Still not a full backtest - no slippage model, no partial fills, no
    overnight or funding cost, and a single instrument.
    """
    if not trades:
        return {"trades": 0}

    returns = [t.net_return if use_net else t.gross_return for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]

    equity, peak, max_dd = 1.0, 1.0, 0.0
    for r in returns:
        equity *= 1.0 + r
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1.0)

    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    ordered = sorted(returns)
    mid = len(ordered) // 2
    median = (
        ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0
    )

    def bucket(key: str) -> Dict[str, Dict[str, object]]:
        groups: Dict[str, List[float]] = {}
        for t, r in zip(trades, returns):
            groups.setdefault(getattr(t, key), []).append(r)
        return {
            name: {
                "trades": len(rs),
                "win_rate": round(sum(1 for r in rs if r > 0) / len(rs), 3),
                "avg_return": round(sum(rs) / len(rs), 5),
            }
            for name, rs in sorted(groups.items())
        }

    return {
        "trades": len(trades),
        "longs": sum(1 for t in trades if t.direction == LONG),
        "shorts": sum(1 for t in trades if t.direction == SHORT),
        "win_rate": round(len(wins) / len(trades), 3),
        "avg_return": round(sum(returns) / len(trades), 5),
        "median_return": round(median, 5),
        "best": round(max(returns), 5),
        "worst": round(min(returns), 5),
        "profit_factor": (
            round(gross_win / gross_loss, 3) if gross_loss > 0 else None
        ),
        "expectancy": round(sum(returns) / len(trades), 5),
        "total_return": round(equity - 1.0, 5),
        "max_drawdown": round(max_dd, 5),
        "avg_bars_held": round(sum(t.bars_held for t in trades) / len(trades), 1),
        "avg_mae": round(sum(t.mae for t in trades) / len(trades), 5),
        "closed_by_end_of_data": sum(1 for t in trades if t.exit_reason == "end_of_data"),
        "by_exit_reason": bucket("exit_reason"),
        "by_entry_source": bucket("entry_source"),
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
POLICIES = {
    "opposite": ExitPolicy.opposite_signal,
    "rsi-level": ExitPolicy.rsi_level,
    "risk": ExitPolicy.risk,
    "combined": ExitPolicy.combined,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="positions",
        description="Run RSI signals through an exit policy and report the trades.",
    )
    parser.add_argument("--csv", required=True, help="CSV of bars with a header row")
    parser.add_argument("--close-column", default="close")
    parser.add_argument("--date-column", default=None)
    parser.add_argument(
        "--exit",
        default="combined",
        choices=sorted(POLICIES) + ["all"],
        help="exit policy; 'all' compares every preset",
    )
    parser.add_argument("--period", type=int, default=14)
    parser.add_argument("--overbought", type=float, default=70.0)
    parser.add_argument("--oversold", type=float, default=30.0)
    parser.add_argument("--cost-bps", type=float, default=0.0, help="per side")
    parser.add_argument("--no-shorts", action="store_true")
    parser.add_argument("--reverse", action="store_true", help="flip, don't flatten")
    parser.add_argument("--last", type=int, default=15, help="trades to print")
    parser.add_argument("--json", action="store_true")
    return parser


def _run(name: str, closes, stamps, signals, values, args) -> Tuple[List[Trade], Dict[str, object]]:
    policy = POLICIES[name]()
    policy = replace(
        policy,
        cost_bps=args.cost_bps,
        allow_shorts=not args.no_shorts,
        reverse_on_opposite=args.reverse or policy.reverse_on_opposite,
    )
    trades = simulate(
        closes, signals, policy, rsi_values=values, rsi_period=args.period, timestamps=stamps
    )
    return trades, summarize_trades(trades)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    stamps, closes = load_csv(args.csv, args.close_column, args.date_column)
    if len(closes) <= args.period:
        print(f"need more than {args.period} bars, got {len(closes)}", file=sys.stderr)
        return 1

    cfg = RsiConfig(period=args.period, overbought=args.overbought, oversold=args.oversold)
    values = rsi(closes, cfg.period, cfg.method)
    signals = generate_signals(closes, stamps, cfg)
    names = sorted(POLICIES) if args.exit == "all" else [args.exit]

    if args.json:
        payload = {}
        for name in names:
            trades, stats = _run(name, closes, stamps, signals, values, args)
            payload[name] = {"stats": stats, "trades": [t.as_dict() for t in trades]}
        print(json.dumps({"bars": len(closes), "signals": len(signals), "policies": payload}, indent=2))
        return 0

    print(f"{args.csv}: {len(closes)} bars, {len(signals)} signals, cost {args.cost_bps} bps/side\n")

    for name in names:
        trades, stats = _run(name, closes, stamps, signals, values, args)
        armed = ", ".join(POLICIES[name]().armed())
        print(f"--- {name} ---")
        print(f"    exits armed: {armed}")
        if not trades:
            print("    no trades\n")
            continue
        print(
            f"    {stats['trades']} trades  win rate {stats['win_rate']}  "
            f"avg {stats['avg_return']:+.4f}  total {stats['total_return']:+.4f}  "
            f"max dd {stats['max_drawdown']:.4f}  pf {stats['profit_factor']}"
        )
        for reason, s in stats["by_exit_reason"].items():  # type: ignore[union-attr]
            print(f"      {reason:<16} n={s['trades']:<4} win={s['win_rate']:<6} avg={s['avg_return']:+.4f}")
        if len(names) == 1:
            print(
                f"\n    {'dir':<6} {'entry':<12} {'exit':<12} {'bars':>5} "
                f"{'net':>9}  entry rule -> exit"
            )
            for t in trades[-args.last :]:
                print(
                    f"    {t.direction:<6} {(t.entry_timestamp or str(t.entry_index)):<12} "
                    f"{(t.exit_timestamp or str(t.exit_index)):<12} {t.bars_held:>5} "
                    f"{t.net_return:>+9.4f}  {t.entry_source} -> {t.exit_reason}"
                )
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
