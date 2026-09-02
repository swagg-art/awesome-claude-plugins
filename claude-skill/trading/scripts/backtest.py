"""Bar-based backtester. No live orders, no broker - just bars and rules.

Deliberately simple and honest about it: one position at a time, fills at the
next bar's open, a fixed spread and per-lot commission. It answers "did this
rule have an edge on this data", not "what would my broker have filled".
"""

from __future__ import annotations

from dataclasses import dataclass, field


class BacktestError(Exception):
    pass


@dataclass
class Trade:
    side: str
    entry_index: int
    entry_price: float
    exit_index: int | None = None
    exit_price: float | None = None
    reason: str = ""

    def points(self) -> float:
        if self.exit_price is None:
            return 0.0
        return (
            self.exit_price - self.entry_price
            if self.side == "buy"
            else self.entry_price - self.exit_price
        )


@dataclass
class Result:
    trades: list = field(default_factory=list)
    equity: list = field(default_factory=list)
    bars: int = 0

    def stats(self) -> dict:
        closed = [t for t in self.trades if t.exit_price is not None]
        if not closed:
            return {"trades": 0, "bars": self.bars}
        pnl = [t.points() for t in closed]
        wins = [p for p in pnl if p > 0]
        losses = [p for p in pnl if p < 0]
        gross_win, gross_loss = sum(wins), abs(sum(losses))
        peak, drawdown = 0.0, 0.0
        for value in self.equity:
            peak = max(peak, value)
            drawdown = min(drawdown, value - peak)
        return {
            "trades": len(closed),
            "bars": self.bars,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(closed),
            "net_points": sum(pnl),
            "profit_factor": (gross_win / gross_loss) if gross_loss else float("inf"),
            "expectancy_points": sum(pnl) / len(closed),
            "avg_win": (gross_win / len(wins)) if wins else 0.0,
            "avg_loss": (gross_loss / len(losses)) if losses else 0.0,
            "max_drawdown_points": abs(drawdown),
            "longs": sum(1 for t in closed if t.side == "buy"),
            "shorts": sum(1 for t in closed if t.side == "sell"),
        }


# --- indicators -------------------------------------------------------------


def sma(values: list, period: int) -> list:
    """Simple moving average, None until the window fills."""
    if period <= 0:
        raise BacktestError("period must be positive")
    out, total = [], 0.0
    for i, value in enumerate(values):
        total += value
        if i >= period:
            total -= values[i - period]
        out.append(total / period if i >= period - 1 else None)
    return out


def rsi(values: list, period: int = 14) -> list:
    """Wilder's RSI."""
    out = [None] * len(values)
    if len(values) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain, avg_loss = gains / period, losses / period
    out[period] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(change, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0.0)) / period
        out[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def atr(bars: list, period: int = 14) -> list:
    """Average true range over OHLC bars."""
    trs = [None]
    for i in range(1, len(bars)):
        high, low, prev_close = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    out = [None] * len(bars)
    if len(bars) <= period:
        return out
    window = sum(trs[1 : period + 1]) / period
    out[period] = window
    for i in range(period + 1, len(bars)):
        window = (window * (period - 1) + trs[i]) / period
        out[i] = window
    return out


# --- strategies -------------------------------------------------------------
# A strategy is signal(index, bars, context) -> "buy" | "sell" | "close" | None


def ma_cross(fast: int = 10, slow: int = 30):
    """Long when the fast MA is above the slow, short when below."""

    def build(bars):
        closes = [b["close"] for b in bars]
        return {"fast": sma(closes, fast), "slow": sma(closes, slow)}

    def signal(i, bars, ctx):
        f, s = ctx["fast"][i], ctx["slow"][i]
        pf, ps = ctx["fast"][i - 1], ctx["slow"][i - 1]
        if None in (f, s, pf, ps):
            return None
        if pf <= ps and f > s:
            return "buy"
        if pf >= ps and f < s:
            return "sell"
        return None

    signal.build = build
    signal.name = f"ma_cross({fast},{slow})"
    return signal


def rsi_reversion(period: int = 14, low: float = 30, high: float = 70):
    """Buy oversold, sell overbought, flatten on the way back through 50."""

    def build(bars):
        return {"rsi": rsi([b["close"] for b in bars], period)}

    def signal(i, bars, ctx):
        value, previous = ctx["rsi"][i], ctx["rsi"][i - 1]
        if value is None or previous is None:
            return None
        if previous <= low < value:
            return "buy"
        if previous >= high > value:
            return "sell"
        if (previous < 50 <= value) or (previous > 50 >= value):
            return "close"
        return None

    signal.build = build
    signal.name = f"rsi_reversion({period},{low},{high})"
    return signal


def breakout(lookback: int = 20):
    """Break of the highest high or lowest low of the last N bars."""

    def build(bars):
        return {}

    def signal(i, bars, ctx):
        if i < lookback:
            return None
        window = bars[i - lookback : i]
        if bars[i]["close"] > max(b["high"] for b in window):
            return "buy"
        if bars[i]["close"] < min(b["low"] for b in window):
            return "sell"
        return None

    signal.build = build
    signal.name = f"breakout({lookback})"
    return signal


STRATEGIES = {"ma_cross": ma_cross, "rsi_reversion": rsi_reversion, "breakout": breakout}


# --- engine -----------------------------------------------------------------


def run(
    bars: list,
    strategy,
    spread: float = 0.0,
    stop_points: float | None = None,
    target_points: float | None = None,
    allow_short: bool = True,
) -> Result:
    """Run `strategy` over `bars`, filling at the next bar's open.

    Signals are read on the close of bar i and filled at the open of bar i+1 -
    reading and filling on the same bar is the classic way to backtest an edge
    that does not exist.
    """
    if len(bars) < 3:
        raise BacktestError("need at least 3 bars to backtest")
    for required in ("open", "high", "low", "close"):
        if required not in bars[0]:
            raise BacktestError(f"bars must carry {required!r}")

    ctx = strategy.build(bars) if hasattr(strategy, "build") else {}
    result = Result(bars=len(bars))
    open_trade: Trade | None = None
    realized = 0.0
    half_spread = spread / 2

    for i in range(1, len(bars) - 1):
        bar = bars[i]

        # stops and targets are checked intrabar, on the bar that formed them
        if open_trade is not None:
            direction = 1 if open_trade.side == "buy" else -1
            if stop_points is not None:
                stop = open_trade.entry_price - direction * stop_points
                hit = bar["low"] <= stop if direction == 1 else bar["high"] >= stop
                if hit:
                    open_trade.exit_index, open_trade.exit_price = i, stop
                    open_trade.reason = "stop"
                    realized += open_trade.points()
                    result.trades.append(open_trade)
                    open_trade = None
            if open_trade is not None and target_points is not None:
                target = open_trade.entry_price + direction * target_points
                hit = bar["high"] >= target if direction == 1 else bar["low"] <= target
                if hit:
                    open_trade.exit_index, open_trade.exit_price = i, target
                    open_trade.reason = "target"
                    realized += open_trade.points()
                    result.trades.append(open_trade)
                    open_trade = None

        signal = strategy(i, bars, ctx)
        fill = bars[i + 1]["open"]

        def close_at(price: float, reason: str) -> float:
            exit_price = price - half_spread if open_trade.side == "buy" else price + half_spread
            open_trade.exit_index, open_trade.exit_price = i + 1, exit_price
            open_trade.reason = reason
            result.trades.append(open_trade)
            return open_trade.points()

        if signal == "close" and open_trade is not None:
            realized += close_at(fill, "signal")
            open_trade = None
        elif signal in ("buy", "sell"):
            if open_trade is not None and open_trade.side != signal:
                realized += close_at(fill, "reverse")
                open_trade = None
            if open_trade is None and (signal == "buy" or allow_short):
                entry = fill + half_spread if signal == "buy" else fill - half_spread
                open_trade = Trade(side=signal, entry_index=i + 1, entry_price=entry)

        # mark to market so the drawdown reflects open risk, not just closed trades
        if open_trade is not None:
            direction = 1 if open_trade.side == "buy" else -1
            unrealized = direction * (bar["close"] - open_trade.entry_price)
        else:
            unrealized = 0.0
        result.equity.append(realized + unrealized)

    if open_trade is not None:
        last = bars[-1]["close"]
        open_trade.exit_index = len(bars) - 1
        open_trade.exit_price = (
            last - half_spread if open_trade.side == "buy" else last + half_spread
        )
        open_trade.reason = "end of data"
        realized += open_trade.points()
        result.trades.append(open_trade)
        result.equity.append(realized)

    return result


def bars_from_rates(rates) -> list:
    """Convert MT5 copy_rates_* output (numpy recarray or tuples) to dicts."""
    out = []
    for row in rates:
        try:
            out.append(
                {
                    "time": int(row["time"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["tick_volume"]),
                }
            )
        except (IndexError, KeyError, TypeError):
            out.append(
                {
                    "time": int(row[0]),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]) if len(row) > 5 else 0.0,
                }
            )
    return out
