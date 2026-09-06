"""Portfolio review checks."""

import unittest

from liquid_assistant.review import review_portfolio


def position(**kwargs):
    base = dict(symbol="BTC", side="long", notional=5_000.0, entry=80_000.0,
                mark=80_000.0, leverage=5.0, stop_loss=78_000.0)
    base.update(kwargs)
    return base


class ReviewTests(unittest.TestCase):
    def test_a_flat_account_says_so(self):
        review = review_portfolio(equity=10_000, available_balance=10_000, positions=[])
        self.assertEqual(review["positions"], 0)
        self.assertIn("Flat", review["headline"])

    def test_a_position_without_a_stop_is_the_headline(self):
        review = review_portfolio(
            equity=10_000, available_balance=5_000,
            positions=[position(stop_loss=None)],
        )
        self.assertEqual(review["unprotected_positions"], 1)
        self.assertIn("no stop", review["headline"])
        self.assertEqual(review["findings"][0]["severity"], "high")

    def test_a_tidy_account_produces_no_high_findings(self):
        review = review_portfolio(
            equity=10_000, available_balance=5_000, positions=[position()],
        )
        self.assertFalse([f for f in review["findings"] if f["severity"] == "high"])

    def test_gross_leverage_is_computed_and_capped(self):
        positions = [position(symbol=s, notional=8_000.0) for s in ("BTC", "ETH")]
        review = review_portfolio(
            equity=10_000, available_balance=1_000, positions=positions,
            max_gross_leverage=1.0,
        )
        self.assertAlmostEqual(review["gross_leverage"], 1.6)
        self.assertTrue(any("account leverage" in f["finding"] for f in review["findings"]))

    def test_a_position_near_liquidation_is_flagged(self):
        # 40x leaves about 2% before liquidation.
        review = review_portfolio(
            equity=10_000, available_balance=1_000,
            positions=[position(leverage=40.0)],
        )
        self.assertTrue(
            any("liquidation" in f["finding"] for f in review["findings"])
        )

    def test_a_stop_already_past_the_mark_is_flagged(self):
        review = review_portfolio(
            equity=10_000, available_balance=5_000,
            positions=[position(mark=77_000.0)],   # long, stop 78,000
        )
        self.assertTrue(
            any("past the mark" in f["finding"] for f in review["findings"])
        )

    def test_crypto_concentration_is_called_one_bet(self):
        positions = [position(symbol=s, notional=1_000.0)
                     for s in ("BTC", "ETH", "SOL")]
        review = review_portfolio(
            equity=10_000, available_balance=5_000, positions=positions,
        )
        self.assertTrue(
            any("one asset class" in f["finding"] for f in review["findings"])
        )

    def test_findings_are_ranked_worst_first(self):
        positions = [
            position(symbol="BTC", stop_loss=None),
            position(symbol="ETH", notional=1_000.0),
        ]
        review = review_portfolio(
            equity=10_000, available_balance=5_000, positions=positions,
        )
        severities = [f["severity"] for f in review["findings"]]
        self.assertEqual(severities, sorted(severities, key={"high": 0, "medium": 1}.get))


if __name__ == "__main__":
    unittest.main()
