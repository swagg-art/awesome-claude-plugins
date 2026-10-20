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

    def test_resample_hourly_to_4h(self):
        hourly = [
            {"t": f"2020-01-01 {h:02d}:00:00", "o": h, "h": h + 1, "l": h - 1, "c": h + 0.5}
            for h in range(8)
        ]
        four = backtest.resample(hourly, "4h")
        self.assertEqual(len(four), 2)
        self.assertEqual((four[0]["o"], four[0]["h"], four[0]["l"], four[0]["c"]), (0, 4, -1, 3.5))
        self.assertEqual(four[1]["t"], "2020-01-01 04:00:00")

    def test_resample_daily_to_month(self):
        daily = [{"t": f"2020-0{m}-{d:02d}", "o": 1, "h": d, "l": 1, "c": d} for m in (1, 2) for d in range(1, 29)]
        self.assertEqual([b["c"] for b in backtest.resample(daily, "1mo")], [28, 28])


if __name__ == "__main__":
    unittest.main()
