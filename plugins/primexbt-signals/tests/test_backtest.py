import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/primexbt-signals/scripts"))
import backtest  # noqa: E402
import signals  # noqa: E402
from test_signals import series  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "backtest/data"


class BacktestTests(unittest.TestCase):
    def test_uptrend_makes_money_long_only(self):
        r = backtest.backtest(series(+0.5, n=200), cost_pct=0)
        self.assertGreater(r["n"], 0)
        self.assertEqual(r["shorts"], 0)
        self.assertGreater(r["total_r"], 0)

    def test_entry_is_next_bar_open(self):
        bars = series(+0.5, n=120)
        r = backtest.backtest(bars, cost_pct=0)
        opens = {b["t"]: b["o"] for b in bars}
        for t in r["trades"]:
            self.assertEqual(t["entry"], opens[t["t_in"]])

    def test_stop_assumed_before_target_in_same_bar(self):
        bars = series(+0.5, n=60)
        first = backtest.backtest(bars, cost_pct=0)["trades"][0]
        i = next(k for k, b in enumerate(bars) if b["t"] == first["t_in"])
        wide = [dict(b) for b in bars[: i + 1]]
        wide[i]["h"], wide[i]["l"] = wide[i]["o"] * 2, wide[i]["o"] / 2  # touches both
        t = backtest.backtest(wide, cost_pct=0)["trades"][0]
        self.assertEqual(t["reason"], "stop")
        self.assertAlmostEqual(t["r"], -1.0, places=6)

    def test_costs_reduce_result(self):
        bars = series(+0.5, n=200)
        self.assertLess(backtest.backtest(bars, cost_pct=0.5)["total_r"], backtest.backtest(bars, cost_pct=0)["total_r"])

    def test_long_only_has_no_shorts(self):
        r = backtest.backtest(series(-0.5, n=200, start=300), long_only=True)
        self.assertEqual(r["shorts"], 0)

    def test_bundled_datasets_run(self):
        for f in DATA.glob("*.csv"):
            for bars in signals.load(f).values():
                self.assertIn("n", backtest.backtest(bars))


if __name__ == "__main__":
    unittest.main()
