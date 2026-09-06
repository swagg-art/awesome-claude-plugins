"""Funding cost checks. A perpetual charges rent; a CFD does not."""

import unittest

from liquid_assistant.funding import break_even_hold_hours, estimate_funding


class FundingTests(unittest.TestCase):
    def test_a_long_pays_when_funding_is_positive(self):
        # $10,000 notional, 1bp per 8h, held 24h = 3 intervals = $3.
        estimate = estimate_funding(
            notional=10_000, side="long", rate_per_interval=0.0001, hold_hours=24,
        )
        self.assertEqual(estimate.intervals, 3)
        self.assertAlmostEqual(estimate.cost, 3.0)

    def test_a_short_is_paid_when_funding_is_positive(self):
        estimate = estimate_funding(
            notional=10_000, side="short", rate_per_interval=0.0001, hold_hours=24,
        )
        self.assertAlmostEqual(estimate.cost, -3.0)
        self.assertIn("pays you", estimate.verdict)

    def test_partial_intervals_are_not_charged(self):
        """Funding is taken at discrete moments, so 7 hours costs nothing."""
        estimate = estimate_funding(
            notional=10_000, side="long", rate_per_interval=0.0001, hold_hours=7,
        )
        self.assertEqual(estimate.intervals, 0)
        self.assertEqual(estimate.cost, 0.0)

    def test_a_long_hold_makes_funding_material(self):
        """27 days — the average hold the MT5 strategy showed on daily bars."""
        estimate = estimate_funding(
            notional=10_000, side="long", rate_per_interval=0.0001,
            hold_hours=27 * 24, reward_amount=200,
        )
        self.assertEqual(estimate.intervals, 81)
        self.assertAlmostEqual(estimate.cost, 81.0)
        self.assertIn("%", estimate.verdict)

    def test_funding_eating_the_target_is_called_out(self):
        estimate = estimate_funding(
            notional=10_000, side="long", rate_per_interval=0.0003,
            hold_hours=30 * 24, reward_amount=200,
        )
        self.assertIn("has to work quickly", estimate.verdict)

    def test_funding_rivalling_the_stop_is_called_out(self):
        estimate = estimate_funding(
            notional=10_000, side="long", rate_per_interval=0.0005,
            hold_hours=10 * 24, risk_amount=100,
        )
        self.assertIn("second, slower stop", estimate.verdict)

    def test_annualised_rate_is_reported(self):
        # 1bp per 8h = 3 per day = 1095 per year = 10.95%
        estimate = estimate_funding(
            notional=1_000, side="long", rate_per_interval=0.0001, hold_hours=8,
        )
        self.assertAlmostEqual(estimate.annualised_rate_pct, 10.95, places=2)

    def test_bad_inputs_are_rejected(self):
        for kwargs in (
            dict(side="buy"), dict(notional=0), dict(hold_hours=-1), dict(interval_hours=0),
        ):
            base = dict(notional=1_000, side="long", rate_per_interval=0.0001,
                        hold_hours=24)
            base.update(kwargs)
            with self.assertRaises(ValueError):
                estimate_funding(**base)


class BreakEvenTests(unittest.TestCase):
    def test_how_long_until_funding_cancels_the_target(self):
        # 2% target, 1bp per 8h -> 200 intervals -> 1600 hours.
        hours = break_even_hold_hours(
            rate_per_interval=0.0001, side="long", reward_pct=0.02,
        )
        self.assertAlmostEqual(hours, 1600.0)

    def test_favourable_funding_never_cancels_anything(self):
        self.assertIsNone(
            break_even_hold_hours(rate_per_interval=0.0001, side="short",
                                  reward_pct=0.02)
        )


if __name__ == "__main__":
    unittest.main()
