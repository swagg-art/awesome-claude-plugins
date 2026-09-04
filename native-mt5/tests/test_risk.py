import unittest

from native_mt5.adapters.base import Deal, SymbolInfo
from native_mt5.risk import (
    RiskError,
    round_to_step,
    size_position,
    summarise_deals,
)

EURUSD = SymbolInfo(
    name="EURUSD",
    description="Euro vs US Dollar",
    digits=5,
    point=0.00001,
    tick_size=0.00001,
    tick_value=1.0,
    contract_size=100_000.0,
    volume_min=0.01,
    volume_max=100.0,
    volume_step=0.01,
    currency_profit="USD",
)


class RoundToStepTests(unittest.TestCase):
    def test_rounds_down_never_up(self):
        self.assertEqual(round_to_step(0.179, 0.01), 0.17)
        self.assertEqual(round_to_step(0.999, 0.1), 0.9)

    def test_exact_multiples_survive_float_noise(self):
        self.assertEqual(round_to_step(0.3, 0.1), 0.3)
        self.assertEqual(round_to_step(0.07, 0.01), 0.07)

    def test_non_positive_step_is_rejected(self):
        with self.assertRaises(RiskError):
            round_to_step(1.0, 0)


class SizePositionTests(unittest.TestCase):
    def test_sizes_to_the_requested_risk(self):
        # 1% of 10,000 = $100. A 20 pip stop on EURUSD costs $200 per lot.
        sized = size_position(
            symbol=EURUSD,
            side="buy",
            entry=1.08500,
            stop_loss=1.08300,
            balance=10_000,
            risk_pct=1.0,
        )
        self.assertEqual(sized.volume, 0.5)
        self.assertEqual(sized.risk_amount, 100.0)
        self.assertEqual(sized.loss_at_stop, 100.0)
        self.assertEqual(sized.stop_distance_points, 200.0)

    def test_reward_risk_ratio_is_reported(self):
        sized = size_position(
            symbol=EURUSD,
            side="buy",
            entry=1.08500,
            stop_loss=1.08300,
            take_profit=1.09100,
            balance=10_000,
            risk_pct=1.0,
        )
        self.assertEqual(sized.reward_risk_ratio, 3.0)

    def test_volume_cap_is_recorded(self):
        sized = size_position(
            symbol=EURUSD,
            side="buy",
            entry=1.08500,
            stop_loss=1.08300,
            balance=10_000,
            risk_pct=1.0,
            max_volume=0.2,
        )
        self.assertEqual(sized.volume, 0.2)
        self.assertEqual(sized.capped_by, "max_order_volume")
        self.assertLess(sized.loss_at_stop, sized.risk_amount)

    def test_a_stop_too_wide_for_the_minimum_lot_is_an_error(self):
        with self.assertRaises(RiskError) as ctx:
            size_position(
                symbol=EURUSD,
                side="buy",
                entry=1.08500,
                stop_loss=1.00000,
                balance=100,
                risk_pct=1.0,
            )
        self.assertIn("minimum", str(ctx.exception))

    def test_stop_on_the_wrong_side_is_rejected(self):
        with self.assertRaises(RiskError):
            size_position(
                symbol=EURUSD, side="buy", entry=1.08, stop_loss=1.09,
                balance=10_000, risk_pct=1.0,
            )
        with self.assertRaises(RiskError):
            size_position(
                symbol=EURUSD, side="sell", entry=1.08, stop_loss=1.07,
                balance=10_000, risk_pct=1.0,
            )

    def test_target_on_the_wrong_side_is_rejected(self):
        with self.assertRaises(RiskError):
            size_position(
                symbol=EURUSD, side="buy", entry=1.08, stop_loss=1.07,
                take_profit=1.06, balance=10_000, risk_pct=1.0,
            )

    def test_zero_distance_stop_is_rejected(self):
        with self.assertRaises(RiskError):
            size_position(
                symbol=EURUSD, side="buy", entry=1.08, stop_loss=1.08,
                balance=10_000, risk_pct=1.0,
            )

    def test_bad_risk_and_balance_are_rejected(self):
        for kwargs in ({"risk_pct": 0}, {"risk_pct": 101}, {"balance": 0}):
            base = dict(
                symbol=EURUSD, side="buy", entry=1.08500, stop_loss=1.08300,
                balance=10_000, risk_pct=1.0,
            )
            base.update(kwargs)
            with self.assertRaises(RiskError):
                size_position(**base)


def deal(profit, commission=0.0, swap=0.0):
    return Deal(
        ticket=1, symbol="EURUSD", side="buy", volume=0.1, price=1.085,
        profit=profit, commission=commission, swap=swap, time="2026-01-01T00:00:00+00:00",
    )


class SummariseDealsTests(unittest.TestCase):
    def test_empty_history_reports_zeroes_not_errors(self):
        summary = summarise_deals([])
        self.assertEqual(summary["trades"], 0)
        self.assertIsNone(summary["profit_factor"])

    def test_headline_stats(self):
        summary = summarise_deals([deal(100), deal(50), deal(-30), deal(-20)])
        self.assertEqual(summary["trades"], 4)
        self.assertEqual(summary["net_profit"], 100.0)
        self.assertEqual(summary["win_rate_pct"], 50.0)
        self.assertEqual(summary["profit_factor"], 3.0)
        self.assertEqual(summary["largest_loss"], -30.0)

    def test_costs_are_netted_into_the_result(self):
        summary = summarise_deals([deal(10, commission=-12.0)])
        self.assertEqual(summary["net_profit"], -2.0)
        self.assertEqual(summary["win_rate_pct"], 0.0)

    def test_all_wins_leaves_profit_factor_undefined(self):
        self.assertIsNone(summarise_deals([deal(10), deal(20)])["profit_factor"])


if __name__ == "__main__":
    unittest.main()
