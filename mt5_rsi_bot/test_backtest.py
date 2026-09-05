"""Fill-mechanics checks for the backtester.

Every case here has a hand-computed expected value. If these pass, the numbers
the backtester reports mean what the report says they mean.

    python test_backtest.py        # or: python -m unittest test_backtest
"""

import unittest

import pandas as pd

from backtest import run_backtest
from config import Config


def setUpModule():
    Config.SL_MODE, Config.SL_PERCENT, Config.TP_PERCENT = "percent", 1.0, 2.0
    Config.LOT_SIZE, Config.RSI_PERIOD = 1.0, 14
    Config.RSI_OVERSOLD, Config.RSI_OVERBOUGHT = 30, 70


def bar(label, o, h, low, c):
    return {"time": f"2026-01-02 {label}", "open": o, "high": h, "low": low, "close": c}


def series(tail):
    """40 falling bars then a sharp up bar, which forces a BUY cross-back.

    The signal is detected on the last of those bars, so the entry fills at the
    open of tail[0], and tail[1] onward decides how the trade ends.
    """
    closes = [1000.0 - 10 * i for i in range(40)] + [700.0]
    warmup = [
        {"time": f"2026-01-01 {i:02d}:00", "open": c, "high": c * 1.001,
         "low": c * 0.999, "close": c}
        for i, c in enumerate(closes)
    ]
    return pd.DataFrame(warmup + tail)


def one_trade(tail, **kwargs):
    kwargs.setdefault("spread", 0.0)
    kwargs.setdefault("contract_size", 1.0)
    kwargs.setdefault("apply_daily_limit", False)
    result = run_backtest(series(tail), **kwargs)
    assert len(result.trades) == 1, f"expected 1 trade, got {len(result.trades)}"
    return result.trades[0]


QUIET = bar("01:00", 700, 701, 699, 700)   # entry bar: touches nothing


class FillTests(unittest.TestCase):
    """Entry at 700 gives a 693 stop (-1%) and a 714 target (+2%)."""

    def test_entry_is_the_open_after_the_signal_bar(self):
        trade = one_trade([QUIET, bar("02:00", 700, 720, 699, 715)])
        self.assertAlmostEqual(trade.entry_price, 700.0)

    def test_target_hit(self):
        trade = one_trade([QUIET, bar("02:00", 700, 720, 699, 715)])
        self.assertEqual(trade.exit_reason, "target")
        self.assertAlmostEqual(trade.exit_price, 714.0)
        self.assertAlmostEqual(trade.pnl, 14.0)

    def test_stop_hit(self):
        trade = one_trade([QUIET, bar("02:00", 700, 701, 690, 692)])
        self.assertEqual(trade.exit_reason, "stop")
        self.assertAlmostEqual(trade.exit_price, 693.0)
        self.assertAlmostEqual(trade.pnl, -7.0)

    def test_a_bar_spanning_both_levels_takes_the_stop(self):
        """The pessimistic choice. Assuming the target is how backtests lie."""
        trade = one_trade([QUIET, bar("02:00", 700, 720, 690, 715)])
        self.assertEqual(trade.exit_reason, "stop")
        self.assertAlmostEqual(trade.exit_price, 693.0)

    def test_a_gap_through_the_stop_fills_at_the_open(self):
        trade = one_trade([QUIET, bar("02:00", 680, 685, 675, 680)])
        self.assertAlmostEqual(trade.exit_price, 680.0)
        self.assertAlmostEqual(trade.pnl, -20.0)

    def test_spread_is_charged_on_a_long_entry(self):
        trade = one_trade([QUIET, bar("02:00", 700, 730, 699, 725)], spread=2.0)
        self.assertAlmostEqual(trade.entry_price, 702.0)
        self.assertAlmostEqual(trade.exit_price, 716.04)   # 702 * 1.02
        self.assertAlmostEqual(trade.pnl, 14.04)

    def test_contract_size_scales_pnl(self):
        trade = one_trade([QUIET, bar("02:00", 700, 720, 699, 715)], contract_size=100.0)
        self.assertAlmostEqual(trade.pnl, 1400.0)


class NoSignalTests(unittest.TestCase):
    def test_flat_market_produces_no_trades(self):
        flat = pd.DataFrame(
            [{"time": f"t{i}", "open": 100, "high": 100.1, "low": 99.9, "close": 100}
             for i in range(60)]
        )
        result = run_backtest(flat, spread=0.0, contract_size=1.0,
                              apply_daily_limit=False)
        self.assertEqual(result.trades, [])


class GuardTests(unittest.TestCase):
    def test_points_mode_without_a_point_size_is_refused(self):
        """SL_PIPS * 0.0 would be a zero-distance stop, silently."""
        Config.SL_MODE = "points"
        try:
            with self.assertRaises(SystemExit):
                run_backtest(series([QUIET]), point=0.0)
        finally:
            Config.SL_MODE = "percent"


if __name__ == "__main__":
    unittest.main()
