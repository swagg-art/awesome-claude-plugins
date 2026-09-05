"""Confirmed RSI strategy: divergence and candlestick confirmation.

The plain version — buy when RSI crosses back above 30 — was backtested and
lost money at every setting tried. The reason is visible in the trade log: RSI
crossing 30 in a downtrend is a pause, not a reversal, and a fixed percentage
stop gets taken out on the continuation.

This module replaces both halves of that.

**Signal.** Reaching the oversold zone only *arms* a setup. Nothing is traded
until price itself confirms, within a limited window, by printing a reversal
candlestick pattern and closing above the previous bar's high. A setup that
never confirms expires unfilled — which is most of them, and that is the point.
Additional weight is given when RSI diverges from price: price making a lower
low while RSI makes a higher low says selling pressure is fading even though
price is not.

**Stops.** Nothing is a fixed percentage. The stop goes below the swing low the
setup formed on, with an ATR buffer so normal noise does not clip it, and the
target is a multiple of whatever that distance turned out to be. When the chart
is quiet the stop is close; when it is wild the stop is far. The risk stays the
same either way, because the position is sized to the distance.

Every function here is pure: candles in, decision out. That is what makes the
backtest and the live bot provably the same strategy.
"""

from dataclasses import dataclass, field

import pandas as pd

# ---------------------------------------------------------------------------
# Candlestick patterns
#
# Each takes a small window of bars ending at the candle being judged, and
# returns True or False. Thresholds are ratios of the candle's own range, so
# they mean the same thing on BTC at $64,000 and EURUSD at 1.08.
# ---------------------------------------------------------------------------


def _parts(candle):
    """Body, range, and the two wicks of one candle."""
    body = abs(candle["close"] - candle["open"])
    rng = candle["high"] - candle["low"]
    upper = candle["high"] - max(candle["close"], candle["open"])
    lower = min(candle["close"], candle["open"]) - candle["low"]
    return body, rng, upper, lower


def is_bullish(candle):
    return candle["close"] > candle["open"]


def is_bearish(candle):
    return candle["close"] < candle["open"]


def bullish_engulfing(window):
    """A down candle wholly swallowed by the up candle that follows it."""
    if len(window) < 2:
        return False
    prev, cur = window[-2], window[-1]
    if not (is_bearish(prev) and is_bullish(cur)):
        return False
    return cur["open"] <= prev["close"] and cur["close"] >= prev["open"]


def bearish_engulfing(window):
    if len(window) < 2:
        return False
    prev, cur = window[-2], window[-1]
    if not (is_bullish(prev) and is_bearish(cur)):
        return False
    return cur["open"] >= prev["close"] and cur["close"] <= prev["open"]


def hammer(window, wick_ratio=2.0):
    """Long lower wick, small body near the top: sellers pushed down and lost."""
    if not window:
        return False
    body, rng, upper, lower = _parts(window[-1])
    if rng <= 0 or body <= 0:
        return False
    return lower >= wick_ratio * body and upper <= body and lower / rng >= 0.5


def shooting_star(window, wick_ratio=2.0):
    """The mirror of a hammer: buyers pushed up and lost."""
    if not window:
        return False
    body, rng, upper, lower = _parts(window[-1])
    if rng <= 0 or body <= 0:
        return False
    return upper >= wick_ratio * body and lower <= body and upper / rng >= 0.5


def piercing_line(window):
    """Opens below the prior down candle's close, closes past its midpoint."""
    if len(window) < 2:
        return False
    prev, cur = window[-2], window[-1]
    if not (is_bearish(prev) and is_bullish(cur)):
        return False
    midpoint = (prev["open"] + prev["close"]) / 2
    return cur["open"] < prev["close"] and prev["close"] < cur["close"] < prev["open"] \
        and cur["close"] > midpoint


def dark_cloud_cover(window):
    if len(window) < 2:
        return False
    prev, cur = window[-2], window[-1]
    if not (is_bullish(prev) and is_bearish(cur)):
        return False
    midpoint = (prev["open"] + prev["close"]) / 2
    return cur["open"] > prev["close"] and prev["close"] > cur["close"] > prev["open"] \
        and cur["close"] < midpoint


def morning_star(window, small_body_ratio=0.5):
    """Big down candle, indecision, then a big up candle reclaiming half of it."""
    if len(window) < 3:
        return False
    first, middle, last = window[-3], window[-2], window[-1]
    first_body = abs(first["close"] - first["open"])
    middle_body = abs(middle["close"] - middle["open"])
    if not (is_bearish(first) and is_bullish(last)) or first_body <= 0:
        return False
    if middle_body > first_body * small_body_ratio:
        return False
    return last["close"] > (first["open"] + first["close"]) / 2


def evening_star(window, small_body_ratio=0.5):
    if len(window) < 3:
        return False
    first, middle, last = window[-3], window[-2], window[-1]
    first_body = abs(first["close"] - first["open"])
    middle_body = abs(middle["close"] - middle["open"])
    if not (is_bullish(first) and is_bearish(last)) or first_body <= 0:
        return False
    if middle_body > first_body * small_body_ratio:
        return False
    return last["close"] < (first["open"] + first["close"]) / 2


BULLISH_PATTERNS = {
    "bullish_engulfing": bullish_engulfing,
    "hammer": hammer,
    "piercing_line": piercing_line,
    "morning_star": morning_star,
}

BEARISH_PATTERNS = {
    "bearish_engulfing": bearish_engulfing,
    "shooting_star": shooting_star,
    "dark_cloud_cover": dark_cloud_cover,
    "evening_star": evening_star,
}


def bullish_patterns_at(window):
    return [name for name, fn in BULLISH_PATTERNS.items() if fn(window)]


def bearish_patterns_at(window):
    return [name for name, fn in BEARISH_PATTERNS.items() if fn(window)]


# ---------------------------------------------------------------------------
# Swing structure
# ---------------------------------------------------------------------------


def swing_lows(lows, left=2, right=2):
    """Indices of bars whose low is the lowest in their neighbourhood.

    `right` bars must exist after a pivot for it to be confirmed, so the most
    recent pivot is always `right` bars old. That lag is real and unavoidable —
    a pivot is not a pivot until price has turned away from it — and pretending
    otherwise is how a backtest reads the future.
    """
    out = []
    for i in range(left, len(lows) - right):
        window = lows[i - left: i + right + 1]
        if lows[i] == min(window) and lows[i] < lows[i - 1]:
            out.append(i)
    return out


def swing_highs(highs, left=2, right=2):
    out = []
    for i in range(left, len(highs) - right):
        window = highs[i - left: i + right + 1]
        if highs[i] == max(window) and highs[i] > highs[i - 1]:
            out.append(i)
    return out


# ---------------------------------------------------------------------------
# Divergence
# ---------------------------------------------------------------------------


@dataclass
class Divergence:
    kind: str            # "bullish" | "bearish"
    first_index: int
    second_index: int
    price_first: float
    price_second: float
    rsi_first: float
    rsi_second: float

    def describe(self):
        direction = "lower low" if self.kind == "bullish" else "higher high"
        rsi_move = "higher" if self.kind == "bullish" else "lower"
        return (
            f"{self.kind} divergence: price {direction} "
            f"({self.price_first:.5g} → {self.price_second:.5g}) while RSI made a "
            f"{rsi_move} one ({self.rsi_first:.1f} → {self.rsi_second:.1f})"
        )


def find_divergence(
    highs, lows, rsi, upto, *, kind="bullish",
    left=2, right=2, max_lookback=60, min_gap=5, rsi_zone=45.0,
):
    """Most recent regular divergence ending at or before bar `upto`.

    Bullish: price made a lower low, RSI made a higher low, with the first pivot
    inside the oversold half of the range. Bearish is the mirror.

    Only data up to `upto` is examined, so this cannot see forward.
    """
    start = max(0, upto - max_lookback)
    series = lows[: upto + 1] if kind == "bullish" else highs[: upto + 1]
    pivots = (
        swing_lows(series, left, right) if kind == "bullish"
        else swing_highs(series, left, right)
    )
    pivots = [p for p in pivots if p >= start]
    if len(pivots) < 2:
        return None

    latest = pivots[-1]
    for earlier in reversed(pivots[:-1]):
        if latest - earlier < min_gap:
            continue
        r_first, r_second = rsi[earlier], rsi[latest]
        if pd.isna(r_first) or pd.isna(r_second):
            continue

        if kind == "bullish":
            price_lower = series[latest] < series[earlier]
            rsi_higher = r_second > r_first
            in_zone = r_first < rsi_zone
            if price_lower and rsi_higher and in_zone:
                return Divergence("bullish", earlier, latest, series[earlier],
                                  series[latest], r_first, r_second)
        else:
            price_higher = series[latest] > series[earlier]
            rsi_lower = r_second < r_first
            in_zone = r_first > 100 - rsi_zone
            if price_higher and rsi_lower and in_zone:
                return Divergence("bearish", earlier, latest, series[earlier],
                                  series[latest], r_first, r_second)
    return None


# ---------------------------------------------------------------------------
# Setups
# ---------------------------------------------------------------------------


@dataclass
class Setup:
    """An armed idea, waiting for price to agree with it."""

    side: str                  # "BUY" | "SELL"
    armed_at: int
    anchor_index: int          # the swing the stop will sit behind
    anchor_price: float        # that swing's low (BUY) or high (SELL)
    reasons: list = field(default_factory=list)
    divergence: object = None

    def expired(self, index, window):
        return index - self.armed_at > window


@dataclass
class Entry:
    side: str
    index: int
    stop_loss: float
    take_profit: float
    reasons: list

    def describe(self):
        return " + ".join(self.reasons)


def arm_setup(df, rsi, i, *, oversold, overbought, left=2, right=2,
              max_lookback=60, rsi_zone=45.0):
    """Is there a reason to start watching for a reversal at bar i?

    Two triggers, and divergence is the stronger one:
      * RSI is in the oversold or overbought zone, or
      * RSI diverges from price.

    Neither one enters a trade. They only arm a setup.
    """
    if pd.isna(rsi[i]):
        return None

    highs, lows = df["high"].tolist(), df["low"].tolist()
    reasons = []

    div = find_divergence(highs, lows, rsi, i, kind="bullish",
                          left=left, right=right, max_lookback=max_lookback,
                          rsi_zone=rsi_zone)
    if div is not None and div.second_index >= i - right - 1:
        return Setup("BUY", i, div.second_index, lows[div.second_index],
                     [div.describe()], div)

    div = find_divergence(highs, lows, rsi, i, kind="bearish",
                          left=left, right=right, max_lookback=max_lookback,
                          rsi_zone=rsi_zone)
    if div is not None and div.second_index >= i - right - 1:
        return Setup("SELL", i, div.second_index, highs[div.second_index],
                     [div.describe()], div)

    if rsi[i] <= oversold:
        anchor = min(range(max(0, i - 10), i + 1), key=lambda j: lows[j])
        reasons.append(f"RSI {rsi[i]:.1f} in the oversold zone (<= {oversold:g})")
        return Setup("BUY", i, anchor, lows[anchor], reasons)

    if rsi[i] >= overbought:
        anchor = max(range(max(0, i - 10), i + 1), key=lambda j: highs[j])
        reasons.append(f"RSI {rsi[i]:.1f} in the overbought zone (>= {overbought:g})")
        return Setup("SELL", i, anchor, highs[anchor], reasons)

    return None


def confirms(df, rsi, i, setup, *, require_pattern=True, require_break=True,
             require_rsi_turn=True):
    """Has price agreed with the setup at bar i? Returns the reasons, or None.

    Three independent confirmations, each switchable:
      * a reversal candlestick pattern closed on this bar
      * this bar closed beyond the previous bar's extreme (momentum)
      * RSI turned in the setup's direction

    The point of demanding agreement is that most armed setups never get it.
    """
    if i < 3 or pd.isna(rsi[i]) or pd.isna(rsi[i - 1]):
        return None

    window = df.iloc[max(0, i - 2): i + 1].to_dict("records")
    prev, cur = window[-2], window[-1]
    reasons = []

    if setup.side == "BUY":
        patterns = bullish_patterns_at(window)
        broke = cur["close"] > prev["high"]
        turned = rsi[i] > rsi[i - 1]
    else:
        patterns = bearish_patterns_at(window)
        broke = cur["close"] < prev["low"]
        turned = rsi[i] < rsi[i - 1]

    if require_pattern:
        if not patterns:
            return None
        reasons.append(patterns[0].replace("_", " "))
    elif patterns:
        reasons.append(patterns[0].replace("_", " "))

    if require_break:
        if not broke:
            return None
        edge = "high" if setup.side == "BUY" else "low"
        reasons.append(f"closed beyond the previous bar's {edge}")
    if require_rsi_turn:
        if not turned:
            return None
        reasons.append(f"RSI turning ({rsi[i - 1]:.1f} → {rsi[i]:.1f})")

    return reasons


def levels_from_structure(setup, entry_price, atr_value, *, atr_buffer=0.5,
                          reward_multiple=2.0, min_stop_atr=0.5):
    """Stop behind the swing, target as a multiple of that distance.

    This is the part that stops being a fixed percentage. The stop sits where
    the idea is wrong — beyond the swing the setup formed on — plus a buffer of
    ATR so ordinary noise does not clip it. The target is then a multiple of
    whatever distance that turned out to be, so a quiet chart gives a near stop
    and a near target, and a wild one gives both far away.

    Returns (stop_loss, take_profit, distance), or None if the structure gives
    no usable stop.
    """
    buffer_ = atr_value * atr_buffer
    floor = atr_value * min_stop_atr

    if setup.side == "BUY":
        stop = setup.anchor_price - buffer_
        distance = entry_price - stop
        if distance < floor:                       # anchor too close, or above entry
            distance = floor
            stop = entry_price - distance
        if distance <= 0:
            return None
        return stop, entry_price + distance * reward_multiple, distance

    stop = setup.anchor_price + buffer_
    distance = stop - entry_price
    if distance < floor:
        distance = floor
        stop = entry_price + distance
    if distance <= 0:
        return None
    return stop, entry_price - distance * reward_multiple, distance


def average_true_range(df, period=14):
    """Wilder's ATR, as a list aligned with df. None until warmed up.

    Used to buffer stops and to floor them: a stop must clear the market's
    ordinary noise or it is only a donation to the spread.
    """
    highs, lows, closes = df["high"].tolist(), df["low"].tolist(), df["close"].tolist()
    out = [None] * len(df)
    if len(df) < period + 1:
        return out

    ranges = [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        for i in range(1, len(df))
    ]
    value = sum(ranges[:period]) / period
    out[period] = value
    for i in range(period, len(ranges)):
        value = (value * (period - 1) + ranges[i]) / period
        out[i + 1] = value
    return out
