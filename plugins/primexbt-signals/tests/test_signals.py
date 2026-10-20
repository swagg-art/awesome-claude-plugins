import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/primexbt-signals/scripts"))
import signals  # noqa: E402


def series(step: float, n: int = 60, start: float = 100.0) -> list[dict]:
    bars, price = [], start
    for i in range(n):
        # small wiggle so RSI stays out of the 0/100 extremes
        drift = step * (1.6 if i % 3 else -0.8)
        o, c = price, price + drift
        bars.append({"t": f"2026-01-{i:03d}", "o": o, "h": max(o, c) + 0.5, "l": min(o, c) - 0.5, "c": c})
        price = c
    return bars


class SignalTests(unittest.TestCase):
    def test_uptrend_is_long_with_levels_above_stop(self):
        r = signals.analyse("UP", series(+0.5))
        self.assertEqual(r["bias"], "LONG")
        self.assertLess(r["levels"]["stop"], r["levels"]["entry"])
        self.assertGreater(r["levels"]["tp2"], r["levels"]["tp1"])

    def test_downtrend_is_short_with_stop_above_entry(self):
        r = signals.analyse("DN", series(-0.5, start=200))
        self.assertEqual(r["bias"], "SHORT")
        self.assertGreater(r["levels"]["stop"], r["levels"]["entry"])

    def test_bar_order_does_not_matter(self):
        bars = series(+0.5)
        self.assertEqual(signals.analyse("A", bars)["score"], signals.analyse("A", bars[::-1])["score"])

    def test_too_few_bars_rejected(self):
        with self.assertRaises(ValueError):
            signals.analyse("X", series(1, n=20))

    def test_example_snapshot_parses(self):
        files = sorted((Path(__file__).resolve().parents[1] / "examples/2026-09-29").glob("*.csv"))
        series_ = {}
        for f in files:
            series_.update(signals.load(f))
        self.assertEqual(set(series_), {"BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "XAUUSD"})


if __name__ == "__main__":
    unittest.main()
