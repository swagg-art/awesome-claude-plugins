"""Tests for the exit-policy / position layer."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rsi.positions import (  # noqa: E402
    LONG,
    SHORT,
    ExitPolicy,
    Trade,
    atr,
    simulate,
    summarize_trades,
)
from rsi.rsi_signals import BUY, SELL, Signal  # noqa: E402


def sig(index, direction, source="test", strength=0.5, price=0.0, rsi_value=50.0):
    return Signal(
        index=index,
        direction=direction,
        source=source,
        rsi=rsi_value,
        price=price,
        strength=strength,
    )


class TestAtr(unittest.TestCase):
    def test_constant_range_gives_that_range(self):
        highs = [11.0] * 40
        lows = [9.0] * 40
        closes = [10.0] * 40
        values = atr(closes, highs, lows, period=14)
        self.assertIsNone(values[13])
        self.assertAlmostEqual(values[-1], 2.0, places=9)

    def test_close_only_falls_back_to_close_to_close(self):
        closes = [100.0 + i for i in range(40)]  # 1.0 per bar
        self.assertAlmostEqual(atr(closes, period=14)[-1], 1.0, places=9)

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            atr([1.0, 2.0, 3.0], highs=[1.0, 2.0], lows=[1.0, 2.0])


class TestFillsAndLookahead(unittest.TestCase):
    def test_entry_is_delayed_by_one_bar_by_default(self):
        closes = [100.0] * 5 + [101.0, 102.0, 103.0, 104.0, 105.0]
        trades = simulate(
            closes, [sig(4, BUY)], ExitPolicy(on_opposite_signal=True), rsi_period=2
        )
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].entry_index, 5, "must fill on the bar after the signal")
        self.assertEqual(trades[0].entry_price, closes[5])

    def test_zero_delay_fills_on_the_signal_bar(self):
        closes = [100.0] * 5 + [101.0, 102.0, 103.0]
        trades = simulate(closes, [sig(4, BUY)], ExitPolicy(entry_delay_bars=0), rsi_period=2)
        self.assertEqual(trades[0].entry_index, 4)

    def test_signal_too_close_to_the_end_never_fills(self):
        closes = [100.0] * 6
        self.assertEqual(simulate(closes, [sig(5, BUY)], rsi_period=2), [])

    def test_exit_always_follows_entry(self):
        closes = [100.0 + (i % 7) for i in range(60)]
        signals = [sig(i, BUY if i % 2 == 0 else SELL) for i in range(10, 50, 6)]
        for policy in (
            ExitPolicy.opposite_signal(),
            ExitPolicy.rsi_level(),
            ExitPolicy.risk(),
            ExitPolicy.combined(),
        ):
            for t in simulate(closes, signals, policy, rsi_period=5):
                self.assertGreater(t.exit_index, t.entry_index)
                self.assertGreaterEqual(t.bars_held, 1)

    def test_negative_delay_raises(self):
        with self.assertRaises(ValueError):
            simulate([1.0, 2.0], [], ExitPolicy(entry_delay_bars=-1))


class TestOppositeSignalExit(unittest.TestCase):
    def setUp(self):
        self.closes = [100.0 + i for i in range(30)]
        self.signals = [sig(2, BUY), sig(10, SELL)]

    def test_contrary_signal_closes_the_position(self):
        policy = ExitPolicy.opposite_signal()
        trades = simulate(self.closes, self.signals, policy, rsi_period=3)
        first = trades[0]
        self.assertEqual(first.direction, LONG)
        self.assertEqual(first.exit_reason, "opposite_signal")
        self.assertEqual(first.exit_index, 11)

    def test_flat_by_default_reversed_on_request(self):
        flat = simulate(self.closes, self.signals, ExitPolicy.opposite_signal(), rsi_period=3)
        flipped = simulate(
            self.closes, self.signals, ExitPolicy.opposite_signal(reverse=True), rsi_period=3
        )
        self.assertEqual([t.direction for t in flat], [LONG])
        self.assertEqual([t.direction for t in flipped], [LONG, SHORT])
        self.assertEqual(flipped[1].entry_index, flipped[0].exit_index)

    def test_disabled_means_the_contrary_signal_is_ignored(self):
        policy = ExitPolicy(on_opposite_signal=False)
        trades = simulate(self.closes, self.signals, policy, rsi_period=3)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].exit_reason, "end_of_data")

    def test_same_direction_signals_do_not_pyramid(self):
        trades = simulate(
            self.closes, [sig(2, BUY), sig(6, BUY), sig(9, BUY)], rsi_period=3
        )
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].entry_index, 3)

    def test_shorts_can_be_disabled(self):
        trades = simulate(
            self.closes,
            [sig(2, SELL), sig(10, BUY)],
            ExitPolicy(allow_shorts=False),
            rsi_period=3,
        )
        self.assertTrue(all(t.direction == LONG for t in trades))


class TestRsiLevelExit(unittest.TestCase):
    def test_long_closes_when_rsi_reaches_the_level(self):
        closes = [100.0] * 20 + [100.0 + i for i in range(20)]
        values = [None] * 5 + [20.0] * 15 + [45.0] * 10 + [72.0] * 10
        trades = simulate(
            closes,
            [sig(6, BUY)],
            ExitPolicy.rsi_level(long_exit=70.0),
            rsi_values=values,
        )
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].exit_reason, "rsi_level")
        self.assertEqual(trades[0].exit_index, 30, "first bar at or above 70")

    def test_short_closes_at_its_own_level(self):
        closes = [100.0] * 40
        values = [None] * 5 + [80.0] * 15 + [55.0] * 10 + [28.0] * 10
        trades = simulate(
            closes, [sig(6, SELL)], ExitPolicy.rsi_level(short_exit=30.0), rsi_values=values
        )
        self.assertEqual(trades[0].direction, SHORT)
        self.assertEqual(trades[0].exit_reason, "rsi_level")
        self.assertEqual(trades[0].exit_index, 30)

    def test_level_never_reached_falls_through_to_end_of_data(self):
        closes = [100.0] * 40
        values = [None] * 5 + [40.0] * 35
        trades = simulate(
            closes, [sig(6, BUY)], ExitPolicy.rsi_level(long_exit=95.0), rsi_values=values
        )
        self.assertEqual(trades[0].exit_reason, "end_of_data")


class TestRiskExits(unittest.TestCase):
    @staticmethod
    def _bars(path):
        """Build OHLC where each bar's range is +/-0.5 around the close."""
        highs = [c + 0.5 for c in path]
        lows = [c - 0.5 for c in path]
        return path, highs, lows

    def test_stop_fills_at_the_stop_level_with_ohlc(self):
        # 30 flat bars (ATR ~1.0 from the wicks), then a slide.
        path = [100.0] * 30 + [100.0 - 2 * i for i in range(1, 12)]
        closes, highs, lows = self._bars(path)
        policy = ExitPolicy.risk(stop_atr=2.0, target_atr=None, atr_period=14)
        trades = simulate(closes, [sig(28, BUY)], policy, highs=highs, lows=lows, rsi_period=5)
        self.assertEqual(len(trades), 1)
        t = trades[0]
        self.assertEqual(t.exit_reason, "atr_stop")
        self.assertLess(t.exit_price, t.entry_price)
        self.assertAlmostEqual(t.exit_price, t.entry_price - 2.0 * 1.0, delta=0.35)

    def test_target_fills_on_the_way_up(self):
        path = [100.0] * 30 + [100.0 + 2 * i for i in range(1, 12)]
        closes, highs, lows = self._bars(path)
        policy = ExitPolicy.risk(stop_atr=5.0, target_atr=3.0, atr_period=14)
        trades = simulate(closes, [sig(28, BUY)], policy, highs=highs, lows=lows, rsi_period=5)
        self.assertEqual(trades[0].exit_reason, "atr_target")
        self.assertGreater(trades[0].net_return, 0)

    def test_stop_wins_when_a_bar_spans_both(self):
        path = [100.0] * 30 + [100.0, 100.0]
        closes = list(path)
        highs = [c + 0.5 for c in path]
        lows = [c - 0.5 for c in path]
        highs[-1], lows[-1] = 130.0, 70.0  # one bar that reaches stop and target
        policy = ExitPolicy.risk(stop_atr=2.0, target_atr=2.0, atr_period=14)
        trades = simulate(closes, [sig(29, BUY)], policy, highs=highs, lows=lows, rsi_period=5)
        self.assertEqual(trades[0].exit_reason, "atr_stop")

    def test_trailing_stop_ratchets_and_never_loosens(self):
        path = [100.0] * 30 + [100.0 + i for i in range(1, 16)] + [110.0, 104.0, 98.0]
        closes, highs, lows = self._bars(path)
        policy = ExitPolicy.risk(stop_atr=None, target_atr=None, trail_atr=2.0, atr_period=14)
        trades = simulate(closes, [sig(28, BUY)], policy, highs=highs, lows=lows, rsi_period=5)
        t = trades[0]
        self.assertEqual(t.exit_reason, "atr_trail")
        self.assertGreater(t.exit_price, t.entry_price, "trail should lock in the run-up")
        self.assertGreater(t.mfe, 0.1)

    def test_time_stop_closes_on_schedule(self):
        closes = [100.0] * 60
        policy = ExitPolicy(time_stop_bars=7, on_opposite_signal=False)
        trades = simulate(closes, [sig(10, BUY)], policy, rsi_period=5)
        self.assertEqual(trades[0].exit_reason, "time_stop")
        self.assertEqual(trades[0].bars_held, 7)

    def test_stops_without_ohlc_fill_at_the_close(self):
        # Zig-zag so close-to-close ATR is ~1.0, then a drop through the stop.
        path = [100.0 + (1.0 if i % 2 else 0.0) for i in range(30)] + [90.0, 88.0]
        policy = ExitPolicy.risk(stop_atr=2.0, target_atr=None, atr_period=14)
        trades = simulate(path, [sig(28, BUY)], policy, rsi_period=5)
        self.assertEqual(trades[0].exit_reason, "atr_stop")
        self.assertEqual(
            trades[0].exit_price, 90.0, "no highs/lows means the fill is the close"
        )

    def test_entry_is_skipped_when_atr_cannot_arm_a_stop(self):
        flat = [100.0] * 40  # close-only and flat -> ATR is zero
        policy = ExitPolicy.risk(stop_atr=2.0, atr_period=14)
        self.assertEqual(simulate(flat, [sig(28, BUY)], policy, rsi_period=5), [])
        allowed = simulate(
            flat,
            [sig(28, BUY)],
            ExitPolicy.risk(stop_atr=2.0, require_atr_for_risk_exits=False),
            rsi_period=5,
        )
        self.assertEqual(len(allowed), 1, "opt out and the unprotected trade is taken")
        self.assertEqual(allowed[0].exit_reason, "end_of_data")

    def test_warmup_signals_are_skipped_by_risk_policies(self):
        path = [100.0 + (i % 3) for i in range(40)]
        trades = simulate(path, [sig(3, BUY)], ExitPolicy.risk(atr_period=14), rsi_period=5)
        self.assertEqual(trades, [], "ATR is undefined that early")


class TestCombinedPolicy(unittest.TestCase):
    def test_all_three_families_are_armed(self):
        armed = ExitPolicy.combined().armed()
        for expected in ("atr_stop", "rsi_level", "opposite_signal"):
            self.assertIn(expected, armed)

    def test_first_condition_to_trigger_wins(self):
        # A hard stop 1 ATR away fires long before RSI could reach 65.
        path = [100.0] * 30 + [99.0, 96.0, 93.0, 90.0]
        highs = [c + 0.5 for c in path]
        lows = [c - 0.5 for c in path]
        policy = ExitPolicy.combined(stop_atr=1.0)
        values = [None] * 5 + [40.0] * len(path[5:])
        trades = simulate(path, [sig(28, BUY)], policy, highs=highs, lows=lows, rsi_values=values)
        self.assertEqual(trades[0].exit_reason, "atr_stop")


class TestCosts(unittest.TestCase):
    def test_costs_are_charged_on_both_sides(self):
        closes = [100.0] * 10 + [110.0] * 10
        signals = [sig(2, BUY), sig(12, SELL)]
        free = simulate(closes, signals, ExitPolicy.opposite_signal(), rsi_period=3)[0]
        charged = simulate(
            closes, signals, ExitPolicy.opposite_signal(cost_bps=25.0), rsi_period=3
        )[0]
        self.assertAlmostEqual(free.gross_return, charged.gross_return, places=9)
        self.assertAlmostEqual(charged.net_return, free.net_return - 0.005, places=9)


class TestExcursions(unittest.TestCase):
    def test_mae_and_mfe_bracket_the_trade(self):
        path = [100.0] * 5 + [95.0, 108.0, 100.0] + [100.0] * 5
        highs = [c + 0.5 for c in path]
        lows = [c - 0.5 for c in path]
        trades = simulate(
            path, [sig(3, BUY)], ExitPolicy(time_stop_bars=8), highs=highs, lows=lows, rsi_period=3
        )
        t = trades[0]
        self.assertLess(t.mae, 0, "a dip below entry must register")
        self.assertGreater(t.mfe, 0, "a rally above entry must register")
        self.assertLessEqual(t.mae, 0.0)


class TestSummary(unittest.TestCase):
    @staticmethod
    def _trade(net, direction=LONG, reason="atr_stop", source="test"):
        return Trade(
            direction=direction,
            entry_index=0,
            entry_price=100.0,
            exit_index=5,
            exit_price=100.0 * (1 + net),
            entry_source=source,
            exit_reason=reason,
            gross_return=net,
            net_return=net,
            bars_held=5,
            mae=-0.01,
            mfe=0.02,
        )

    def test_empty(self):
        self.assertEqual(summarize_trades([]), {"trades": 0})

    def test_headline_numbers(self):
        trades = [self._trade(0.10), self._trade(-0.05), self._trade(0.05), self._trade(-0.10)]
        stats = summarize_trades(trades)
        self.assertEqual(stats["trades"], 4)
        self.assertEqual(stats["win_rate"], 0.5)
        self.assertAlmostEqual(stats["profit_factor"], 1.0, places=6)
        self.assertEqual(stats["best"], 0.1)
        self.assertEqual(stats["worst"], -0.1)

    def test_drawdown_is_negative_after_a_loss(self):
        stats = summarize_trades([self._trade(0.2), self._trade(-0.3)])
        self.assertLess(stats["max_drawdown"], 0)

    def test_breakdowns_partition_the_trades(self):
        trades = [
            self._trade(0.1, reason="atr_target", source="oversold_exit"),
            self._trade(-0.1, reason="atr_stop", source="bullish_divergence"),
        ]
        stats = summarize_trades(trades)
        self.assertEqual(
            sum(v["trades"] for v in stats["by_exit_reason"].values()), len(trades)
        )
        self.assertEqual(
            sum(v["trades"] for v in stats["by_entry_source"].values()), len(trades)
        )

    def test_profit_factor_is_none_without_losses(self):
        self.assertIsNone(summarize_trades([self._trade(0.1)])["profit_factor"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
