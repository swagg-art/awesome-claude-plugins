"""RSI indicators and trading-signal generation.

Pure standard library (no numpy/pandas required) so it drops into any
environment: a backtest script, a bot loop, or an MCP tool wrapper.

Contents
--------
* ``rsi``              - Wilder's RSI (default) and Cutler's SMA variant.
* ``StreamingRsi``     - O(1) incremental RSI for live/streaming bars.
* ``stoch_rsi``        - Stochastic RSI with %K / %D lines.
* ``generate_signals`` - Buy/sell signals from five independent rules.
* ``evaluate_signals`` - Quick forward-return scorecard for the signals.

Timing / lookahead
------------------
Every signal is stamped with the index of the bar on which it can first be
acted on, using only closed-bar data up to that index:

* Threshold, centerline, failure-swing and StochRSI signals fire on the close
  of the crossing bar (tradeable at the next open).
* Divergence signals fire ``pivot_window`` bars after the pivot they rely on,
  because a pivot is not confirmed until that many bars have printed.

Nothing here peeks at future prices, so the output can be fed straight into a
backtester without inflating results.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "Signal",
    "RsiConfig",
    "StreamingRsi",
    "rsi",
    "stoch_rsi",
    "generate_signals",
    "evaluate_signals",
]

BUY = "BUY"
SELL = "SELL"


# --------------------------------------------------------------------------- #
# Core indicator
# --------------------------------------------------------------------------- #
def rsi(
    closes: Sequence[float],
    period: int = 14,
    method: str = "wilder",
) -> List[Optional[float]]:
    """Relative Strength Index, aligned 1:1 with ``closes``.

    The first ``period`` entries are ``None`` (the indicator is undefined
    until ``period`` price changes exist).

    Parameters
    ----------
    closes:
        Closing prices, oldest first.
    period:
        Lookback length. 14 is Wilder's original.
    method:
        ``"wilder"`` uses Wilder's smoothing (the standard everywhere from
        TradingView to Alpha Vantage). ``"sma"`` is Cutler's RSI, a plain
        rolling average that is not path dependent.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    if method not in ("wilder", "sma"):
        raise ValueError("method must be 'wilder' or 'sma'")

    out: List[Optional[float]] = [None] * len(closes)
    if len(closes) <= period:
        return out

    gains: List[float] = [0.0]
    losses: List[float] = [0.0]
    for prev, cur in zip(closes, closes[1:]):
        change = cur - prev
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    if method == "sma":
        for i in range(period, len(closes)):
            window = slice(i - period + 1, i + 1)
            out[i] = _rsi_from_averages(
                sum(gains[window]) / period, sum(losses[window]) / period
            )
        return out

    # Wilder: seed with a simple average, then smooth.
    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    out[period] = _rsi_from_averages(avg_gain, avg_loss)

    for i in range(period + 1, len(closes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i] = _rsi_from_averages(avg_gain, avg_loss)

    return out


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    if avg_gain == 0.0:
        return 0.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


class StreamingRsi:
    """Incremental RSI for live bars: O(1) memory and O(1) per update.

    >>> s = StreamingRsi(period=14)
    >>> for price in prices:            # doctest: +SKIP
    ...     value = s.update(price)     # None until warm, then float
    """

    def __init__(self, period: int = 14) -> None:
        if period < 1:
            raise ValueError("period must be >= 1")
        self.period = period
        self.value: Optional[float] = None
        self._prev_close: Optional[float] = None
        self._avg_gain = 0.0
        self._avg_loss = 0.0
        self._seed_gains: List[float] = []
        self._seed_losses: List[float] = []
        self._warm = False

    def update(self, close: float) -> Optional[float]:
        """Feed one closed bar; returns the current RSI or ``None`` if warming."""
        if self._prev_close is None:
            self._prev_close = close
            return None

        change = close - self._prev_close
        self._prev_close = close
        gain, loss = max(change, 0.0), max(-change, 0.0)

        if not self._warm:
            self._seed_gains.append(gain)
            self._seed_losses.append(loss)
            if len(self._seed_gains) < self.period:
                return None
            self._avg_gain = sum(self._seed_gains) / self.period
            self._avg_loss = sum(self._seed_losses) / self.period
            self._warm = True
        else:
            n = self.period
            self._avg_gain = (self._avg_gain * (n - 1) + gain) / n
            self._avg_loss = (self._avg_loss * (n - 1) + loss) / n

        self.value = _rsi_from_averages(self._avg_gain, self._avg_loss)
        return self.value


def stoch_rsi(
    rsi_values: Sequence[Optional[float]],
    period: int = 14,
    k_smooth: int = 3,
    d_smooth: int = 3,
) -> Tuple[List[Optional[float]], List[Optional[float]]]:
    """Stochastic RSI -> (%K, %D), both scaled 0-100 and aligned to input.

    Where RSI sits inside its own recent range. It turns well before RSI does,
    which makes it early but noisy - treat it as a trigger, not a thesis.
    """
    n = len(rsi_values)
    raw: List[Optional[float]] = [None] * n
    for i in range(n):
        window = rsi_values[max(0, i - period + 1) : i + 1]
        if len(window) < period or any(v is None for v in window):
            continue
        lo, hi = min(window), max(window)  # type: ignore[type-var]
        raw[i] = 50.0 if hi == lo else 100.0 * (rsi_values[i] - lo) / (hi - lo)  # type: ignore[operator]

    k = _smooth(raw, k_smooth)
    d = _smooth(k, d_smooth)
    return k, d


def _smooth(values: Sequence[Optional[float]], length: int) -> List[Optional[float]]:
    if length <= 1:
        return list(values)
    out: List[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        window = values[max(0, i - length + 1) : i + 1]
        if len(window) < length or any(v is None for v in window):
            continue
        out[i] = sum(window) / length  # type: ignore[arg-type]
    return out


# --------------------------------------------------------------------------- #
# Signals
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Signal:
    """One actionable signal, stamped with the bar it may first be acted on."""

    index: int
    direction: str  # BUY | SELL
    source: str  # which rule produced it
    rsi: float
    price: float
    strength: float  # 0..1 heuristic confidence
    timestamp: Optional[str] = None
    note: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "direction": self.direction,
            "source": self.source,
            "rsi": round(self.rsi, 2),
            "price": self.price,
            "strength": round(self.strength, 2),
            "note": self.note,
        }


@dataclass
class RsiConfig:
    """Which rules run, and with what thresholds.

    Defaults are the textbook mean-reversion setup. In a strong trend, shift
    the bands (e.g. 80/40 for an uptrend, 60/20 for a downtrend) rather than
    fading every extreme reading.
    """

    period: int = 14
    method: str = "wilder"
    overbought: float = 70.0
    oversold: float = 30.0

    # Rule toggles
    use_threshold: bool = True  # exit from overbought/oversold
    use_centerline: bool = False  # 50-line crosses (trend following)
    use_divergence: bool = True
    use_failure_swings: bool = True
    use_stoch_rsi: bool = False

    # Divergence / pivot detection
    pivot_window: int = 3  # bars required either side of a pivot
    divergence_lookback: int = 60  # max bars between the two pivots

    # StochRSI
    stoch_period: int = 14
    stoch_k: int = 3
    stoch_d: int = 3

    # Post-processing
    cooldown_bars: int = 3  # suppress same-direction repeats within N bars
    min_strength: float = 0.0


def generate_signals(
    closes: Sequence[float],
    timestamps: Optional[Sequence[str]] = None,
    config: Optional[RsiConfig] = None,
) -> List[Signal]:
    """Run every enabled rule over ``closes`` and return signals, oldest first."""
    cfg = config or RsiConfig()
    if timestamps is not None and len(timestamps) != len(closes):
        raise ValueError("timestamps and closes must be the same length")

    values = rsi(closes, period=cfg.period, method=cfg.method)
    signals: List[Signal] = []

    if cfg.use_threshold:
        signals += _threshold_signals(closes, values, cfg)
    if cfg.use_centerline:
        signals += _centerline_signals(closes, values, cfg)
    if cfg.use_divergence:
        signals += _divergence_signals(closes, values, cfg)
    if cfg.use_failure_swings:
        signals += _failure_swing_signals(closes, values, cfg)
    if cfg.use_stoch_rsi:
        signals += _stoch_rsi_signals(closes, values, cfg)

    signals = [s for s in signals if s.strength >= cfg.min_strength]
    signals.sort(key=lambda s: (s.index, s.source))
    signals = _apply_cooldown(signals, cfg.cooldown_bars)

    if timestamps is not None:
        signals = [
            Signal(**{**s.__dict__, "timestamp": timestamps[s.index]}) for s in signals
        ]
    return signals


def _threshold_signals(
    closes: Sequence[float], values: Sequence[Optional[float]], cfg: RsiConfig
) -> List[Signal]:
    """Classic mean reversion: buy the exit from oversold, sell the exit from overbought.

    Waiting for the cross back through the band (rather than buying the moment
    RSI prints < 30) is what keeps this rule out of the middle of a crash.
    """
    out: List[Signal] = []
    for i in range(1, len(values)):
        prev, cur = values[i - 1], values[i]
        if prev is None or cur is None:
            continue
        if prev <= cfg.oversold < cur:
            depth = cfg.oversold - min(prev, cfg.oversold)
            out.append(
                Signal(
                    index=i,
                    direction=BUY,
                    source="oversold_exit",
                    rsi=cur,
                    price=closes[i],
                    strength=_clamp(0.5 + depth / 60.0),
                    note=f"RSI crossed back above {cfg.oversold:g} (low {prev:.1f})",
                )
            )
        elif prev >= cfg.overbought > cur:
            height = max(prev, cfg.overbought) - cfg.overbought
            out.append(
                Signal(
                    index=i,
                    direction=SELL,
                    source="overbought_exit",
                    rsi=cur,
                    price=closes[i],
                    strength=_clamp(0.5 + height / 60.0),
                    note=f"RSI crossed back below {cfg.overbought:g} (high {prev:.1f})",
                )
            )
    return out


def _centerline_signals(
    closes: Sequence[float], values: Sequence[Optional[float]], cfg: RsiConfig
) -> List[Signal]:
    """Trend following: the 50 line as a momentum regime switch."""
    out: List[Signal] = []
    for i in range(1, len(values)):
        prev, cur = values[i - 1], values[i]
        if prev is None or cur is None:
            continue
        if prev <= 50.0 < cur:
            out.append(
                Signal(
                    index=i,
                    direction=BUY,
                    source="centerline_cross_up",
                    rsi=cur,
                    price=closes[i],
                    strength=0.45,
                    note="RSI crossed above 50 - momentum turned positive",
                )
            )
        elif prev >= 50.0 > cur:
            out.append(
                Signal(
                    index=i,
                    direction=SELL,
                    source="centerline_cross_down",
                    rsi=cur,
                    price=closes[i],
                    strength=0.45,
                    note="RSI crossed below 50 - momentum turned negative",
                )
            )
    return out


def _divergence_signals(
    closes: Sequence[float], values: Sequence[Optional[float]], cfg: RsiConfig
) -> List[Signal]:
    """Regular divergence between price pivots and RSI at those pivots.

    Bullish: price makes a lower low while RSI makes a higher low.
    Bearish: price makes a higher high while RSI makes a lower high.

    The signal is dated ``pivot_window`` bars after the confirming pivot, since
    that is the first bar on which the pivot is knowable.
    """
    out: List[Signal] = []
    w = cfg.pivot_window

    for a, b in _consecutive(_pivots(closes, w, low=True)):
        if b - a > cfg.divergence_lookback:
            continue
        if values[a] is None or values[b] is None:
            continue
        price_lower_low = closes[b] < closes[a]
        rsi_higher_low = values[b] > values[a]  # type: ignore[operator]
        if not (price_lower_low and rsi_higher_low):
            continue
        confirm = b + w
        if confirm >= len(closes):
            continue
        gap = values[b] - values[a]  # type: ignore[operator]
        oversold_context = values[b] < 50.0  # type: ignore[operator]
        out.append(
            Signal(
                index=confirm,
                direction=BUY,
                source="bullish_divergence",
                rsi=values[confirm] if values[confirm] is not None else values[b],  # type: ignore[arg-type]
                price=closes[confirm],
                strength=_clamp((0.55 if oversold_context else 0.4) + gap / 50.0),
                note=(
                    f"price {closes[a]:.4g}->{closes[b]:.4g} (lower low) vs "
                    f"RSI {values[a]:.1f}->{values[b]:.1f} (higher low)"
                ),
            )
        )

    for a, b in _consecutive(_pivots(closes, w, low=False)):
        if b - a > cfg.divergence_lookback:
            continue
        if values[a] is None or values[b] is None:
            continue
        price_higher_high = closes[b] > closes[a]
        rsi_lower_high = values[b] < values[a]  # type: ignore[operator]
        if not (price_higher_high and rsi_lower_high):
            continue
        confirm = b + w
        if confirm >= len(closes):
            continue
        gap = values[a] - values[b]  # type: ignore[operator]
        overbought_context = values[b] > 50.0  # type: ignore[operator]
        out.append(
            Signal(
                index=confirm,
                direction=SELL,
                source="bearish_divergence",
                rsi=values[confirm] if values[confirm] is not None else values[b],  # type: ignore[arg-type]
                price=closes[confirm],
                strength=_clamp((0.55 if overbought_context else 0.4) + gap / 50.0),
                note=(
                    f"price {closes[a]:.4g}->{closes[b]:.4g} (higher high) vs "
                    f"RSI {values[a]:.1f}->{values[b]:.1f} (lower high)"
                ),
            )
        )

    return out


def _failure_swing_signals(
    closes: Sequence[float], values: Sequence[Optional[float]], cfg: RsiConfig
) -> List[Signal]:
    """Wilder's failure swings - his own preferred RSI signal, price-independent.

    Bullish: RSI dips below the oversold band, rallies to a local high, pulls
    back *without* re-entering the band, then breaks that local high.
    Bearish is the mirror image around the overbought band.
    """
    out: List[Signal] = []

    # Bullish
    state = "idle"  # idle -> dipped -> pullback
    peak = 0.0
    for i in range(1, len(values)):
        prev, cur = values[i - 1], values[i]
        if prev is None or cur is None:
            continue
        if cur < cfg.oversold:
            state, peak = "dipped", 0.0
            continue
        if state == "dipped":
            peak = max(peak, cur)
            if cur < prev and peak > cfg.oversold:
                state = "pullback"
        elif state == "pullback":
            if cur > peak:
                out.append(
                    Signal(
                        index=i,
                        direction=BUY,
                        source="bullish_failure_swing",
                        rsi=cur,
                        price=closes[i],
                        strength=_clamp(0.6 + (cur - peak) / 40.0),
                        note=f"RSI held above {cfg.oversold:g} and broke its swing high {peak:.1f}",
                    )
                )
                state, peak = "idle", 0.0
            elif cur > prev:
                peak = max(peak, cur)

    # Bearish
    state, trough = "idle", 100.0
    for i in range(1, len(values)):
        prev, cur = values[i - 1], values[i]
        if prev is None or cur is None:
            continue
        if cur > cfg.overbought:
            state, trough = "spiked", 100.0
            continue
        if state == "spiked":
            trough = min(trough, cur)
            if cur > prev and trough < cfg.overbought:
                state = "bounce"
        elif state == "bounce":
            if cur < trough:
                out.append(
                    Signal(
                        index=i,
                        direction=SELL,
                        source="bearish_failure_swing",
                        rsi=cur,
                        price=closes[i],
                        strength=_clamp(0.6 + (trough - cur) / 40.0),
                        note=f"RSI failed to retake {cfg.overbought:g} and broke its swing low {trough:.1f}",
                    )
                )
                state, trough = "idle", 100.0
            elif cur < prev:
                trough = min(trough, cur)

    return out


def _stoch_rsi_signals(
    closes: Sequence[float], values: Sequence[Optional[float]], cfg: RsiConfig
) -> List[Signal]:
    """%K crossing %D inside the extremes - an early, noisy trigger."""
    k, d = stoch_rsi(values, cfg.stoch_period, cfg.stoch_k, cfg.stoch_d)
    out: List[Signal] = []
    for i in range(1, len(k)):
        if None in (k[i - 1], k[i], d[i - 1], d[i]):
            continue
        crossed_up = k[i - 1] <= d[i - 1] and k[i] > d[i]  # type: ignore[operator]
        crossed_down = k[i - 1] >= d[i - 1] and k[i] < d[i]  # type: ignore[operator]
        current_rsi = values[i] if values[i] is not None else 50.0
        if crossed_up and k[i] < 30.0:  # type: ignore[operator]
            out.append(
                Signal(
                    index=i,
                    direction=BUY,
                    source="stochrsi_cross_up",
                    rsi=current_rsi,  # type: ignore[arg-type]
                    price=closes[i],
                    strength=0.4,
                    note=f"StochRSI %K crossed above %D at {k[i]:.1f}",
                )
            )
        elif crossed_down and k[i] > 70.0:  # type: ignore[operator]
            out.append(
                Signal(
                    index=i,
                    direction=SELL,
                    source="stochrsi_cross_down",
                    rsi=current_rsi,  # type: ignore[arg-type]
                    price=closes[i],
                    strength=0.4,
                    note=f"StochRSI %K crossed below %D at {k[i]:.1f}",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _pivots(values: Sequence[float], window: int, low: bool) -> List[int]:
    """Indices of local extremes with ``window`` bars of confirmation each side."""
    out: List[int] = []
    for i in range(window, len(values) - window):
        seg = values[i - window : i + window + 1]
        pivot = values[i]
        if low and pivot == min(seg) and pivot < values[i - 1] and pivot <= values[i + 1]:
            out.append(i)
        elif not low and pivot == max(seg) and pivot > values[i - 1] and pivot >= values[i + 1]:
            out.append(i)
    return out


def _consecutive(items: Sequence[int]) -> Iterable[Tuple[int, int]]:
    return zip(items, items[1:])


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _apply_cooldown(signals: List[Signal], cooldown: int) -> List[Signal]:
    """Drop same-direction repeats fired within ``cooldown`` bars of the last one."""
    if cooldown <= 0:
        return signals
    kept: List[Signal] = []
    last: Dict[str, int] = {}
    for s in signals:
        prev = last.get(s.direction)
        if prev is not None and s.index - prev < cooldown:
            continue
        kept.append(s)
        last[s.direction] = s.index
    return kept


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def evaluate_signals(
    closes: Sequence[float], signals: Sequence[Signal], horizon: int = 5
) -> Dict[str, object]:
    """Forward-return scorecard: did the signals point the right way?

    Not a backtest - no position sizing, costs, or overlap handling. It is a
    sanity check on whether a parameter set is worth backtesting properly.
    """
    rows: List[Tuple[Signal, float]] = []
    for s in signals:
        target = s.index + horizon
        if target >= len(closes) or closes[s.index] == 0:
            continue
        ret = (closes[target] - closes[s.index]) / closes[s.index]
        rows.append((s, ret if s.direction == BUY else -ret))

    def summarize(subset: List[Tuple[Signal, float]]) -> Dict[str, object]:
        if not subset:
            return {"count": 0, "hit_rate": None, "avg_return": None}
        wins = sum(1 for _, r in subset if r > 0)
        return {
            "count": len(subset),
            "hit_rate": round(wins / len(subset), 3),
            "avg_return": round(sum(r for _, r in subset) / len(subset), 5),
        }

    by_source: Dict[str, object] = {}
    for source in sorted({s.source for s, _ in rows}):
        by_source[source] = summarize([(s, r) for s, r in rows if s.source == source])

    return {
        "horizon": horizon,
        "evaluated": len(rows),
        "skipped_near_end": len(signals) - len(rows),
        "overall": summarize(rows),
        "buy": summarize([(s, r) for s, r in rows if s.direction == BUY]),
        "sell": summarize([(s, r) for s, r in rows if s.direction == SELL]),
        "by_source": by_source,
    }


# --------------------------------------------------------------------------- #
# Data loading + CLI
# --------------------------------------------------------------------------- #
def load_csv(
    path: str, close_column: str = "close", date_column: Optional[str] = None
) -> Tuple[List[str], List[float]]:
    """Read a CSV of bars, oldest first. Returns (timestamps, closes)."""
    stamps: List[str] = []
    closes: List[float] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no header row")
        columns = {name.strip().lower(): name for name in reader.fieldnames}
        close_key = columns.get(close_column.lower())
        if close_key is None:
            raise ValueError(
                f"column {close_column!r} not found; available: {sorted(columns)}"
            )
        date_key = columns.get((date_column or "date").lower()) or columns.get("timestamp")
        for row_number, row in enumerate(reader, start=2):
            raw = (row.get(close_key) or "").strip()
            if not raw:
                continue
            try:
                value = float(raw)
            except ValueError as exc:
                raise ValueError(f"{path}:{row_number}: bad close {raw!r}") from exc
            closes.append(value)
            stamps.append((row.get(date_key) or "").strip() if date_key else str(len(closes)))
    if stamps and len(stamps) > 1 and stamps[0] > stamps[-1]:
        stamps.reverse()
        closes.reverse()
    return stamps, closes


def fetch_alpha_vantage(
    symbol: str, function: str = "TIME_SERIES_DAILY", api_key: Optional[str] = None
) -> Tuple[List[str], List[float]]:
    """Pull daily closes from Alpha Vantage. Needs ALPHAVANTAGE_API_KEY."""
    from urllib.parse import urlencode
    from urllib.request import urlopen

    key = api_key or os.environ.get("ALPHAVANTAGE_API_KEY")
    if not key:
        raise RuntimeError("set ALPHAVANTAGE_API_KEY or pass --api-key")

    query = urlencode(
        {"function": function, "symbol": symbol, "outputsize": "full", "apikey": key}
    )
    with urlopen(f"https://www.alphavantage.co/query?{query}", timeout=30) as response:
        payload = json.load(response)

    series_key = next((k for k in payload if "Time Series" in k), None)
    if series_key is None:
        raise RuntimeError(f"unexpected response: {json.dumps(payload)[:300]}")

    series = payload[series_key]
    stamps = sorted(series)  # oldest first
    closes = [float(series[d]["4. close"]) for d in stamps]
    return stamps, closes


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rsi_signals",
        description="Compute RSI and print buy/sell signals.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--csv", help="CSV file of bars, with a header row")
    source.add_argument("--symbol", help="fetch daily bars from Alpha Vantage")
    parser.add_argument("--close-column", default="close")
    parser.add_argument("--date-column", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--period", type=int, default=14)
    parser.add_argument("--method", choices=["wilder", "sma"], default="wilder")
    parser.add_argument("--overbought", type=float, default=70.0)
    parser.add_argument("--oversold", type=float, default=30.0)
    parser.add_argument("--cooldown", type=int, default=3)
    parser.add_argument("--pivot-window", type=int, default=3)
    parser.add_argument("--centerline", action="store_true", help="enable 50-line crosses")
    parser.add_argument("--stoch", action="store_true", help="enable StochRSI crosses")
    parser.add_argument("--no-divergence", action="store_true")
    parser.add_argument("--no-failure-swings", action="store_true")
    parser.add_argument("--horizon", type=int, default=5, help="forward bars for scoring")
    parser.add_argument("--last", type=int, default=20, help="how many signals to print")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.csv:
        stamps, closes = load_csv(args.csv, args.close_column, args.date_column)
    else:
        stamps, closes = fetch_alpha_vantage(args.symbol, api_key=args.api_key)

    if len(closes) <= args.period:
        print(
            f"need more than {args.period} bars, got {len(closes)}", file=sys.stderr
        )
        return 1

    cfg = RsiConfig(
        period=args.period,
        method=args.method,
        overbought=args.overbought,
        oversold=args.oversold,
        use_centerline=args.centerline,
        use_divergence=not args.no_divergence,
        use_failure_swings=not args.no_failure_swings,
        use_stoch_rsi=args.stoch,
        cooldown_bars=args.cooldown,
        pivot_window=args.pivot_window,
    )

    values = rsi(closes, cfg.period, cfg.method)
    signals = generate_signals(closes, stamps, cfg)
    score = evaluate_signals(closes, signals, args.horizon)
    latest = values[-1]

    if args.json:
        print(
            json.dumps(
                {
                    "bars": len(closes),
                    "last_close": closes[-1],
                    "last_rsi": round(latest, 2) if latest is not None else None,
                    "signals": [s.as_dict() for s in signals],
                    "scorecard": score,
                },
                indent=2,
            )
        )
        return 0

    label = args.symbol or args.csv
    state = "-"
    if latest is not None:
        state = (
            "overbought"
            if latest >= cfg.overbought
            else "oversold" if latest <= cfg.oversold else "neutral"
        )
    print(f"{label}: {len(closes)} bars, last close {closes[-1]:.4g}")
    print(
        f"RSI({cfg.period},{cfg.method}) = "
        f"{'n/a' if latest is None else format(latest, '.2f')}  [{state}]"
    )
    print(f"\n{len(signals)} signals ({args.last} most recent shown)")
    print(f"{'bar':>6}  {'date':<12} {'side':<4} {'rsi':>6} {'price':>10}  {'str':>4}  source")
    for s in signals[-args.last :]:
        stamp = (s.timestamp or "")[:12]
        print(
            f"{s.index:>6}  {stamp:<12} {s.direction:<4} {s.rsi:>6.1f} "
            f"{s.price:>10.4g}  {s.strength:>4.2f}  {s.source}"
        )

    overall = score["overall"]  # type: ignore[index]
    print(f"\nforward-return check ({args.horizon} bars, no costs):")
    print(
        f"  n={overall['count']}  hit rate={overall['hit_rate']}  "  # type: ignore[index]
        f"avg move in signal direction={overall['avg_return']}"  # type: ignore[index]
    )
    for source, stats in score["by_source"].items():  # type: ignore[union-attr]
        print(
            f"  {source:<24} n={stats['count']:<4} hit={stats['hit_rate']} "  # type: ignore[index]
            f"avg={stats['avg_return']}"  # type: ignore[index]
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
