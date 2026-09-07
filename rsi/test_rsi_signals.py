"""Tests for rsi_signals: stdlib unittest, no fixtures, no network."""

from __future__ import annotations

import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rsi.rsi_signals import (  # noqa: E402
    BUY,
    SELL,
    RsiConfig,
    StreamingRsi,
    evaluate_signals,
    generate_signals,
    load_csv,
    rsi,
    stoch_rsi,
)

# Wilder's worked example from "New Concepts in Technical Trading Systems".
WILDER_CLOSES = [
    44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
    45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64,
    46.21, 46.25, 45.71, 46.45, 45.78, 45.35, 44.03, 44.18, 44.22, 44.57,
    43.42, 42.66, 43.13,
]
WILDER_RSI_14 = [
    70.46, 66.25, 66.48, 69.35, 66.29, 57.92, 62.88, 63.21, 56.01, 62.34,
    54.67, 50.39, 40.02, 41.49, 41.90, 45.50, 37.32, 33.09, 37.79,
]


class TestRsi(unittest.TestCase):
    def test_matches_wilder_reference_values(self):
        values = rsi(WILDER_CLOSES, period=14)
        self.assertIsNone(values[13], "RSI is undefined before period+1 bars")
        for offset, expected in enumerate(WILDER_RSI_14):
            with self.subTest(bar=14 + offset):
                self.assertAlmostEqual(values[14 + offset], expected, delta=0.01)

    def test_output_is_aligned_with_input(self):
        values = rsi(WILDER_CLOSES, period=14)
        self.assertEqual(len(values), len(WILDER_CLOSES))
        self.assertEqual(values[:14], [None] * 14)

    def test_too_few_bars_is_all_none(self):
        self.assertEqual(rsi([1.0, 2.0, 3.0], period=14), [None] * 3)
        self.assertEqual(rsi([], period=14), [])

    def test_monotonic_series_saturate(self):
        self.assertAlmostEqual(rsi([float(i) for i in range(40)], 14)[-1], 100.0)
        self.assertAlmostEqual(rsi([float(40 - i) for i in range(40)], 14)[-1], 0.0)

    def test_flat_series_is_neutral(self):
        self.assertAlmostEqual(rsi([10.0] * 40, 14)[-1], 50.0)

    def test_sma_method_differs_but_stays_in_range(self):
        wilder = rsi(WILDER_CLOSES, 14, "wilder")
        cutler = rsi(WILDER_CLOSES, 14, "sma")
        self.assertNotAlmostEqual(wilder[-1], cutler[-1], places=3)
        for value in cutler[14:]:
            self.assertTrue(0.0 <= value <= 100.0)

    def test_invalid_arguments_raise(self):
        with self.assertRaises(ValueError):
            rsi(WILDER_CLOSES, period=0)
        with self.assertRaises(ValueError):
            rsi(WILDER_CLOSES, method="ema")


class TestStreamingRsi(unittest.TestCase):
    def test_agrees_with_batch_computation(self):
        streamer = StreamingRsi(period=14)
        streamed = [streamer.update(price) for price in WILDER_CLOSES]
        batch = rsi(WILDER_CLOSES, period=14)
        for i, (live, ref) in enumerate(zip(streamed, batch)):
            with self.subTest(bar=i):
                if ref is None:
                    self.assertIsNone(live)
                else:
                    self.assertAlmostEqual(live, ref, places=9)


class TestStochRsi(unittest.TestCase):
    def test_bounded_and_aligned(self):
        values = rsi([math.sin(i / 5) * 10 + 100 for i in range(120)], 14)
        k, d = stoch_rsi(values, 14, 3, 3)
        self.assertEqual(len(k), len(values))
        self.assertEqual(len(d), len(values))
        for series in (k, d):
            for value in (v for v in series if v is not None):
                self.assertTrue(0.0 <= value <= 100.0)


class TestSignals(unittest.TestCase):
    @staticmethod
    def _v_shape():
        """Down 40 bars then up 40 - drives RSI through both bands."""
        return [100.0 - i for i in range(40)] + [60.0 + i for i in range(40)]

    def test_oversold_exit_produces_a_buy(self):
        closes = self._v_shape()
        cfg = RsiConfig(use_divergence=False, use_failure_swings=False)
        signals = generate_signals(closes, config=cfg)
        buys = [s for s in signals if s.direction == BUY]
        self.assertTrue(buys, "a V-shaped recovery must yield a buy")
        first = buys[0]
        self.assertEqual(first.source, "oversold_exit")
        self.assertGreater(first.index, 39, "buy must come after the low")

    def test_overbought_exit_produces_a_sell(self):
        closes = [50.0 + i for i in range(40)] + [90.0 - i for i in range(40)]
        cfg = RsiConfig(use_divergence=False, use_failure_swings=False)
        sells = [s for s in generate_signals(closes, config=cfg) if s.direction == SELL]
        self.assertTrue(sells)
        self.assertEqual(sells[0].source, "overbought_exit")

    def test_no_signals_on_a_flat_market(self):
        self.assertEqual(generate_signals([25.0] * 200), [])

    def test_signals_are_sorted_and_never_look_ahead(self):
        closes = self._v_shape()
        cfg = RsiConfig(use_centerline=True, use_stoch_rsi=True)
        signals = generate_signals(closes, config=cfg)
        self.assertEqual([s.index for s in signals], sorted(s.index for s in signals))
        for s in signals:
            self.assertLess(s.index, len(closes))
            self.assertEqual(s.price, closes[s.index])
            self.assertGreaterEqual(s.index, cfg.period)

    def test_divergence_is_dated_after_its_pivot(self):
        # Two lows: the second is lower in price but shallower in momentum.
        closes = (
            [100.0 - i * 2 for i in range(20)]      # slide into oversold
            + [62.0 + i for i in range(12)]         # bounce
            + [74.0 - i * 0.7 for i in range(18)]   # slower slide to a lower low
            + [61.5 + i * 0.9 for i in range(20)]   # recovery
        )
        cfg = RsiConfig(
            use_threshold=False, use_failure_swings=False, pivot_window=3, cooldown_bars=0
        )
        divergences = [
            s for s in generate_signals(closes, config=cfg) if s.source == "bullish_divergence"
        ]
        self.assertTrue(divergences, "expected a bullish divergence in this series")
        for s in divergences:
            self.assertGreaterEqual(s.index, cfg.pivot_window)

    @staticmethod
    def _choppy():
        """Mixed-frequency oscillation: many closely spaced swings."""
        return [
            100.0 + 12 * math.sin(i / 7) + 5 * math.sin(i / 2.3) + 3 * math.sin(i / 23)
            for i in range(400)
        ]

    def test_cooldown_suppresses_same_direction_repeats(self):
        closes = self._choppy()
        loose = generate_signals(closes, config=RsiConfig(cooldown_bars=0))
        tight = generate_signals(closes, config=RsiConfig(cooldown_bars=25))
        self.assertLess(len(tight), len(loose))
        for direction in (BUY, SELL):
            indices = [s.index for s in tight if s.direction == direction]
            gaps = [b - a for a, b in zip(indices, indices[1:])]
            self.assertTrue(all(gap >= 25 for gap in gaps), gaps)

    def test_wider_bands_are_more_selective(self):
        closes = self._choppy()
        default = generate_signals(closes, config=RsiConfig())
        trending = generate_signals(closes, config=RsiConfig(overbought=80, oversold=40))
        extreme = generate_signals(closes, config=RsiConfig(overbought=95, oversold=5))
        self.assertLess(len(trending), len(default))
        self.assertLess(len(extreme), len(trending))

    def test_timestamps_are_attached(self):
        closes = self._v_shape()
        stamps = [f"2026-01-{i + 1:03d}" for i in range(len(closes))]
        for s in generate_signals(closes, stamps):
            self.assertEqual(s.timestamp, stamps[s.index])

    def test_mismatched_timestamps_raise(self):
        with self.assertRaises(ValueError):
            generate_signals([1.0, 2.0, 3.0], ["a", "b"])

    def test_strength_stays_in_unit_range(self):
        closes = [100.0 + 20 * math.sin(i / 4) for i in range(300)]
        cfg = RsiConfig(use_centerline=True, use_stoch_rsi=True, cooldown_bars=0)
        for s in generate_signals(closes, config=cfg):
            self.assertTrue(0.0 <= s.strength <= 1.0, s)


class TestEvaluate(unittest.TestCase):
    def test_scorecard_shape_and_skips(self):
        closes = [100.0 - i for i in range(40)] + [60.0 + i for i in range(40)]
        signals = generate_signals(closes, config=RsiConfig())
        report = evaluate_signals(closes, signals, horizon=5)
        self.assertEqual(report["horizon"], 5)
        self.assertEqual(
            report["evaluated"] + report["skipped_near_end"], len(signals)
        )
        for bucket in ("overall", "buy", "sell"):
            self.assertIn("hit_rate", report[bucket])

    def test_empty_signal_set(self):
        report = evaluate_signals([1.0, 2.0, 3.0], [], horizon=1)
        self.assertEqual(report["overall"], {"count": 0, "hit_rate": None, "avg_return": None})


class TestLoadCsv(unittest.TestCase):
    def _write(self, text):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8"
        )
        handle.write(text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_reads_oldest_first(self):
        path = self._write("date,close\n2026-01-01,10\n2026-01-02,11\n")
        stamps, closes = load_csv(path)
        self.assertEqual(closes, [10.0, 11.0])
        self.assertEqual(stamps[0], "2026-01-01")

    def test_reverses_newest_first_files(self):
        path = self._write("date,close\n2026-01-03,12\n2026-01-02,11\n2026-01-01,10\n")
        stamps, closes = load_csv(path)
        self.assertEqual(closes, [10.0, 11.0, 12.0])
        self.assertEqual(stamps[0], "2026-01-01")

    def test_column_names_are_case_insensitive(self):
        path = self._write("Date,Close\n2026-01-01,10\n2026-01-02,11\n")
        _, closes = load_csv(path)
        self.assertEqual(closes, [10.0, 11.0])

    def test_missing_column_and_bad_value_raise(self):
        with self.assertRaises(ValueError):
            load_csv(self._write("date,open\n2026-01-01,10\n"))
        with self.assertRaises(ValueError):
            load_csv(self._write("date,close\n2026-01-01,abc\n"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
