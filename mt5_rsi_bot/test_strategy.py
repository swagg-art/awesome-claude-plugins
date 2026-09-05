"""Checks for the pattern, divergence and level logic.

Candles are hand-built so each expected answer is obvious by eye.

    python -m unittest test_strategy
"""

import unittest

import pandas as pd

from strategy import (
    Setup,
    bearish_engulfing,
    bullish_engulfing,
    dark_cloud_cover,
    evening_star,
    find_divergence,
    hammer,
    levels_from_structure,
    morning_star,
    passes_trend_filter,
    piercing_line,
    shooting_star,
    swing_highs,
    swing_lows,
)


def c(o, h, low, cl):
    return {"open": o, "high": h, "low": low, "close": cl}


class EngulfingTests(unittest.TestCase):
    def test_bullish_engulfing(self):
        down = c(110, 111, 99, 100)
        up = c(99, 113, 98, 112)          # swallows the whole body
        self.assertTrue(bullish_engulfing([down, up]))

    def test_not_engulfing_when_body_is_smaller(self):
        down = c(110, 111, 99, 100)
        small_up = c(101, 106, 100, 105)  # closes inside the prior body
        self.assertFalse(bullish_engulfing([down, small_up]))

    def test_bullish_engulfing_needs_a_down_candle_first(self):
        up1, up2 = c(100, 112, 99, 110), c(99, 115, 98, 114)
        self.assertFalse(bullish_engulfing([up1, up2]))

    def test_bearish_engulfing(self):
        up = c(100, 111, 99, 110)
        down = c(111, 112, 98, 99)
        self.assertTrue(bearish_engulfing([up, down]))

    def test_engulfing_needs_two_candles(self):
        self.assertFalse(bullish_engulfing([c(1, 2, 0, 1)]))


class WickTests(unittest.TestCase):
    def test_hammer(self):
        # body 2, lower wick 10, upper wick 1
        self.assertTrue(hammer([c(108, 111, 98, 110)]))

    def test_not_a_hammer_without_the_wick(self):
        self.assertFalse(hammer([c(100, 111, 99, 110)]))

    def test_shooting_star(self):
        # body 2, upper wick 10, lower wick 1
        self.assertTrue(shooting_star([c(100, 112, 99, 102)]))

    def test_a_hammer_is_not_a_shooting_star(self):
        candle = c(108, 111, 98, 110)
        self.assertTrue(hammer([candle]))
        self.assertFalse(shooting_star([candle]))

    def test_doji_with_no_body_is_neither(self):
        flat = c(100, 105, 95, 100)
        self.assertFalse(hammer([flat]))
        self.assertFalse(shooting_star([flat]))


class TwoCandleTests(unittest.TestCase):
    def test_piercing_line(self):
        down = c(110, 111, 99, 100)       # midpoint 105
        up = c(98, 108, 97, 106)          # opens below 100, closes above 105
        self.assertTrue(piercing_line([down, up]))

    def test_piercing_line_must_close_past_the_midpoint(self):
        down = c(110, 111, 99, 100)
        weak = c(98, 104, 97, 103)        # closes below 105
        self.assertFalse(piercing_line([down, weak]))

    def test_dark_cloud_cover(self):
        up = c(100, 111, 99, 110)         # midpoint 105
        down = c(112, 113, 100, 102)
        self.assertTrue(dark_cloud_cover([up, down]))


class ThreeCandleTests(unittest.TestCase):
    def test_morning_star(self):
        first = c(110, 111, 99, 100)      # big down, midpoint 105
        middle = c(99, 101, 97, 99.5)     # small body
        last = c(100, 110, 99, 108)       # closes above 105
        self.assertTrue(morning_star([first, middle, last]))

    def test_morning_star_rejects_a_large_middle_body(self):
        first = c(110, 111, 99, 100)
        middle = c(100, 101, 90, 91)      # body 9, not indecision
        last = c(92, 110, 91, 108)
        self.assertFalse(morning_star([first, middle, last]))

    def test_evening_star(self):
        first = c(100, 111, 99, 110)      # midpoint 105
        middle = c(110, 112, 109, 110.5)
        last = c(110, 111, 99, 100)       # closes below 105
        self.assertTrue(evening_star([first, middle, last]))


class SwingTests(unittest.TestCase):
    def test_finds_a_v_bottom(self):
        lows = [10, 9, 8, 5, 8, 9, 10]
        self.assertIn(3, swing_lows(lows, left=2, right=2))

    def test_finds_a_peak(self):
        highs = [1, 2, 3, 9, 3, 2, 1]
        self.assertIn(3, swing_highs(highs, left=2, right=2))

    def test_pivots_need_room_on_the_right(self):
        """The last bars cannot be pivots yet — that lag is real, not a bug."""
        lows = [10, 9, 8, 5]
        self.assertEqual(swing_lows(lows, left=2, right=2), [])


class DivergenceTests(unittest.TestCase):
    def build(self, lows, rsi_values):
        highs = [x + 5 for x in lows]
        return highs, lows, pd.Series(rsi_values).to_numpy()

    def test_bullish_divergence_found(self):
        # Two V bottoms: the second is lower in price but higher in RSI.
        lows = [20, 18, 10, 18, 20, 22, 20, 18, 8, 18, 20]
        rsi = [40, 35, 25, 35, 45, 50, 45, 38, 32, 40, 45]
        highs, lows, rsi = self.build(lows, rsi)
        div = find_divergence(highs, lows, rsi, len(lows) - 1,
                              kind="bullish", min_gap=3)
        self.assertIsNotNone(div)
        self.assertEqual(div.kind, "bullish")
        self.assertLess(div.price_second, div.price_first)   # lower low
        self.assertGreater(div.rsi_second, div.rsi_first)    # higher RSI low

    def test_no_divergence_when_rsi_agrees_with_price(self):
        lows = [20, 18, 10, 18, 20, 22, 20, 18, 8, 18, 20]
        rsi = [40, 35, 30, 35, 45, 50, 45, 30, 20, 30, 40]  # RSI also lower
        highs, lows, rsi = self.build(lows, rsi)
        self.assertIsNone(
            find_divergence(highs, lows, rsi, len(lows) - 1, kind="bullish", min_gap=3)
        )

    def test_divergence_cannot_see_past_upto(self):
        """Guards against the classic lookahead bug."""
        lows = [20, 18, 10, 18, 20, 22, 20, 18, 8, 18, 20]
        rsi = [40, 35, 25, 35, 45, 50, 45, 38, 32, 40, 45]
        highs, lows, rsi = self.build(lows, rsi)
        early = find_divergence(highs, lows, rsi, 5, kind="bullish", min_gap=3)
        self.assertIsNone(early)


class LevelTests(unittest.TestCase):
    """Stops come from the swing, not from a percentage."""

    def test_buy_stop_sits_below_the_swing_with_an_atr_buffer(self):
        setup = Setup("BUY", armed_at=10, anchor_index=8, anchor_price=95.0)
        stop, target, distance = levels_from_structure(
            setup, entry_price=100.0, atr_value=2.0, atr_buffer=0.5,
            reward_multiple=2.0,
        )
        self.assertAlmostEqual(stop, 94.0)        # 95 - (2 * 0.5)
        self.assertAlmostEqual(distance, 6.0)     # 100 - 94
        self.assertAlmostEqual(target, 112.0)     # 100 + 6 * 2

    def test_sell_levels_mirror(self):
        setup = Setup("SELL", armed_at=10, anchor_index=8, anchor_price=105.0)
        stop, target, distance = levels_from_structure(
            setup, entry_price=100.0, atr_value=2.0, atr_buffer=0.5,
            reward_multiple=2.0,
        )
        self.assertAlmostEqual(stop, 106.0)
        self.assertAlmostEqual(distance, 6.0)
        self.assertAlmostEqual(target, 88.0)

    def test_a_stop_too_close_is_pushed_out_to_the_atr_floor(self):
        setup = Setup("BUY", armed_at=10, anchor_index=9, anchor_price=99.9)
        stop, _, distance = levels_from_structure(
            setup, entry_price=100.0, atr_value=2.0, atr_buffer=0.0,
            min_stop_atr=0.5,
        )
        self.assertAlmostEqual(distance, 1.0)     # 2.0 * 0.5
        self.assertAlmostEqual(stop, 99.0)

    def test_volatility_moves_the_stop(self):
        """The whole point: the same setup gives different levels as ATR changes."""
        setup = Setup("BUY", armed_at=10, anchor_index=8, anchor_price=95.0)
        quiet = levels_from_structure(setup, 100.0, atr_value=0.5)
        wild = levels_from_structure(setup, 100.0, atr_value=8.0)
        self.assertGreater(wild[2], quiet[2])


if __name__ == "__main__":
    unittest.main()


class TrendFilterTests(unittest.TestCase):
    """The direction filter shared by the live bot and the backtester."""

    def test_no_trend_value_lets_everything_through(self):
        self.assertTrue(passes_trend_filter("BUY", 100.0, None))
        self.assertTrue(passes_trend_filter("SELL", 100.0, None))

    def test_nan_trend_lets_everything_through(self):
        """The EMA is NaN until it warms up; that must not silently block trades."""
        nan = float("nan")
        self.assertTrue(passes_trend_filter("BUY", 100.0, nan))
        self.assertTrue(passes_trend_filter("SELL", 100.0, nan))

    def test_buy_needs_price_above_the_ema(self):
        self.assertTrue(passes_trend_filter("BUY", 105.0, 100.0))
        self.assertFalse(passes_trend_filter("BUY", 95.0, 100.0))

    def test_sell_needs_price_below_the_ema(self):
        self.assertTrue(passes_trend_filter("SELL", 95.0, 100.0))
        self.assertFalse(passes_trend_filter("SELL", 105.0, 100.0))

    def test_price_exactly_on_the_ema_is_rejected_both_ways(self):
        self.assertFalse(passes_trend_filter("BUY", 100.0, 100.0))
        self.assertFalse(passes_trend_filter("SELL", 100.0, 100.0))

    def test_long_only_drops_sells_regardless_of_trend(self):
        self.assertFalse(passes_trend_filter("SELL", 95.0, 100.0, long_only=True))
        self.assertFalse(passes_trend_filter("SELL", 95.0, None, long_only=True))
        self.assertTrue(passes_trend_filter("BUY", 105.0, 100.0, long_only=True))

    def test_no_action_never_passes(self):
        self.assertFalse(passes_trend_filter(None, 100.0, 50.0))
