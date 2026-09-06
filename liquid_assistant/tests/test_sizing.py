"""Sizing checks, every expected value computed by hand."""

import unittest

from liquid_assistant.sizing import (
    MIN_COLLATERAL,
    SizingError,
    liquidation_price,
    size_trade,
)

ACCOUNT = dict(equity=10_000.0, available_balance=5_000.0)


class LiquidationPriceTests(unittest.TestCase):
    def test_a_long_liquidates_below_entry(self):
        # 10x survives 1/10 - 0.005 = 9.5%, so 100000 * (1 - 0.095) = 90500
        self.assertAlmostEqual(liquidation_price(100_000, "long", 10), 90_500.0)

    def test_a_short_liquidates_above_entry(self):
        self.assertAlmostEqual(liquidation_price(100_000, "short", 10), 109_500.0)

    def test_higher_leverage_brings_liquidation_closer(self):
        far = liquidation_price(100_000, "long", 2)
        near = liquidation_price(100_000, "long", 20)
        self.assertLess(far, near)

    def test_leverage_past_the_maintenance_floor_is_refused(self):
        """At 200x with a 0.5% maintenance margin there is no survivable move."""
        with self.assertRaises(SizingError):
            liquidation_price(100_000, "long", 200)


class SizeTradeTests(unittest.TestCase):
    def test_notional_follows_from_risk_and_stop_distance(self):
        # 1% of 10,000 = $100 risk. A 2% stop means $100 / 0.02 = $5,000 notional.
        trade = size_trade(
            symbol="BTC", side="long", entry=80_000, stop_loss=78_400,
            risk_pct=1.0, **ACCOUNT,
        )
        self.assertAlmostEqual(trade.stop_distance_pct, 2.0)
        self.assertAlmostEqual(trade.notional, 5_000.0)
        self.assertAlmostEqual(trade.risk_amount, 100.0)

    def test_the_stop_really_does_cost_the_risk_budget(self):
        trade = size_trade(
            symbol="BTC", side="long", entry=80_000, stop_loss=78_400,
            risk_pct=1.0, **ACCOUNT,
        )
        loss = trade.notional * (trade.entry - trade.stop_loss) / trade.entry
        self.assertAlmostEqual(loss, trade.risk_amount, places=2)

    def test_leverage_is_the_lowest_that_fits_the_balance(self):
        """Lowest, not highest: it maximises the distance to liquidation."""
        # $5,000 notional into $5,000 available needs exactly 1x.
        trade = size_trade(
            symbol="BTC", side="long", entry=80_000, stop_loss=78_400,
            risk_pct=1.0, **ACCOUNT,
        )
        self.assertEqual(trade.leverage, 1.0)
        self.assertAlmostEqual(trade.collateral, 5_000.0)

    def test_a_smaller_balance_forces_more_leverage(self):
        trade = size_trade(
            symbol="BTC", side="long", entry=80_000, stop_loss=78_400,
            equity=10_000.0, available_balance=1_000.0, risk_pct=1.0,
        )
        self.assertGreaterEqual(trade.leverage, 5.0)
        self.assertLessEqual(trade.collateral, 1_000.0)

    def test_shorts_are_sized_the_same_way(self):
        trade = size_trade(
            symbol="BTC", side="short", entry=80_000, stop_loss=81_600,
            risk_pct=1.0, **ACCOUNT,
        )
        self.assertAlmostEqual(trade.notional, 5_000.0)
        self.assertGreater(trade.liquidation_price, trade.entry)

    def test_reward_risk_is_reported(self):
        trade = size_trade(
            symbol="BTC", side="long", entry=80_000, stop_loss=78_400,
            take_profit=83_200, risk_pct=1.0, **ACCOUNT,
        )
        self.assertAlmostEqual(trade.reward_risk_ratio, 2.0)

    def test_a_target_worth_less_than_the_stop_is_flagged(self):
        trade = size_trade(
            symbol="BTC", side="long", entry=80_000, stop_loss=78_400,
            take_profit=80_800, risk_pct=1.0, **ACCOUNT,
        )
        self.assertTrue(any("less than the stop costs" in w for w in trade.warnings))


class SafetyTests(unittest.TestCase):
    """The cases that stop an account being destroyed by the venue itself."""

    def test_liquidation_always_sits_beyond_the_stop(self):
        for stop_pct in (0.005, 0.01, 0.02, 0.05, 0.10):
            entry = 80_000
            trade = size_trade(
                symbol="BTC", side="long", entry=entry,
                stop_loss=entry * (1 - stop_pct), risk_pct=1.0, **ACCOUNT,
            )
            self.assertGreater(
                trade.liquidation_distance_pct, trade.stop_distance_pct,
                f"a {stop_pct:.1%} stop would be liquidated before it is hit",
            )

    def test_no_safe_leverage_is_refused_rather_than_fudged(self):
        """The trap this whole module exists for.

        $4,000 of exposure squeezed into $200 needs 20x, but a 5% stop needs
        9.5x or less to keep liquidation twice the stop distance away. There is
        no leverage satisfying both, and saying so is the correct answer.
        """
        with self.assertRaises(SizingError) as ctx:
            size_trade(
                symbol="BTC", side="long", entry=80_000, stop_loss=76_000,
                equity=10_000.0, available_balance=200.0, risk_pct=2.0,
            )
        self.assertIn("no safe leverage", str(ctx.exception))

    def test_the_collateral_shortfall_advises_a_wider_stop_not_a_tighter_one(self):
        """notional = risk / stop distance, so tightening needs MORE collateral."""
        with self.assertRaises(SizingError) as ctx:
            size_trade(
                symbol="BTC", side="long", entry=80_000, stop_loss=79_600,
                equity=10_000.0, available_balance=300.0, risk_pct=2.0,
            )
        message = str(ctx.exception)
        self.assertIn("wider stop", message)
        self.assertIn("tightening it needs more collateral", message)
        self.assertIn("most you can risk", message)

    def test_when_no_stop_width_can_help_it_says_so(self):
        """Risk x buffer must fit in the balance, whatever the stop distance.

        $200 of risk with a 2x liquidation buffer needs $400 of collateral. On
        $300 available, no stop width rescues it — only risking less does, and
        the message has to say that rather than suggest a wider stop.
        """
        with self.assertRaises(SizingError) as ctx:
            size_trade(symbol="BTC", side="long", entry=80_000, stop_loss=68_000,
                       equity=10_000.0, available_balance=300.0, risk_pct=2.0)
        message = str(ctx.exception)
        self.assertIn("No stop width fixes this", message)

    def test_the_suggested_risk_reduction_actually_works(self):
        """Every remedy the module offers has to produce a sizeable trade."""
        import re
        kwargs = dict(symbol="BTC", side="long", entry=80_000, stop_loss=68_000,
                      equity=10_000.0, available_balance=300.0)
        with self.assertRaises(SizingError) as ctx:
            size_trade(risk_pct=2.0, **kwargs)
        suggested = float(re.search(r"Risk at most ([\d.]+)%", str(ctx.exception)).group(1))
        # Just inside the number it gave, to clear the boundary.
        trade = size_trade(risk_pct=suggested * 0.98, **kwargs)
        self.assertLessEqual(trade.collateral, 300.0)
        self.assertGreaterEqual(
            trade.liquidation_distance_pct, trade.stop_distance_pct * 2 * 0.99
        )

    def test_the_suggested_wider_stop_actually_works(self):
        """When widening can help, the level it names has to be sizeable."""
        import re
        kwargs = dict(symbol="BTC", side="long", entry=80_000,
                      equity=10_000.0, available_balance=1_000.0, risk_pct=2.0)
        with self.assertRaises(SizingError) as ctx:
            size_trade(stop_loss=79_920, **kwargs)   # 0.1% stop
        match = re.search(r"widen the stop past ([\d.]+)%", str(ctx.exception))
        if match:   # only asserted when this branch is the one taken
            needed = float(match.group(1)) / 100
            trade = size_trade(stop_loss=80_000 * (1 - needed * 1.05), **kwargs)
            self.assertLessEqual(trade.collateral, 1_000.0)

    def test_an_oversized_ask_names_the_shortfall(self):
        with self.assertRaises(SizingError) as ctx:
            size_trade(
                symbol="BTC", side="long", entry=80_000, stop_loss=79_920,
                equity=100_000.0, available_balance=100.0, risk_pct=5.0,
            )
        message = str(ctx.exception)
        self.assertTrue("collateral" in message or "safe leverage" in message)

    def test_below_the_venue_minimum_is_refused_with_a_workable_number(self):
        trade_kwargs = dict(
            symbol="BTC", side="long", entry=80_000, stop_loss=72_000,
            equity=100.0, available_balance=100.0, risk_pct=0.1,
        )
        with self.assertRaises(SizingError) as ctx:
            size_trade(**trade_kwargs)
        self.assertIn(f"${MIN_COLLATERAL:,.0f}", str(ctx.exception))

    def test_a_stop_inside_the_noise_is_flagged(self):
        trade = size_trade(
            symbol="BTC", side="long", entry=80_000, stop_loss=79_960,
            equity=1_000_000.0, available_balance=500_000.0, risk_pct=0.01,
        )
        self.assertTrue(any("noise" in w for w in trade.warnings))


class ValidationTests(unittest.TestCase):
    def test_a_stop_on_the_wrong_side_is_rejected(self):
        with self.assertRaises(SizingError):
            size_trade(symbol="BTC", side="long", entry=80_000, stop_loss=81_000,
                       risk_pct=1.0, **ACCOUNT)
        with self.assertRaises(SizingError):
            size_trade(symbol="BTC", side="short", entry=80_000, stop_loss=79_000,
                       risk_pct=1.0, **ACCOUNT)

    def test_a_target_on_the_wrong_side_is_rejected(self):
        with self.assertRaises(SizingError):
            size_trade(symbol="BTC", side="long", entry=80_000, stop_loss=78_400,
                       take_profit=77_000, risk_pct=1.0, **ACCOUNT)

    def test_unknown_side_is_rejected(self):
        with self.assertRaises(SizingError):
            size_trade(symbol="BTC", side="buy", entry=80_000, stop_loss=78_400,
                       risk_pct=1.0, **ACCOUNT)

    def test_an_unfunded_account_is_rejected(self):
        with self.assertRaises(SizingError) as ctx:
            size_trade(symbol="BTC", side="long", entry=80_000, stop_loss=78_400,
                       equity=10_000.0, available_balance=0.0, risk_pct=1.0)
        self.assertIn("fund the account", str(ctx.exception))

    def test_absurd_risk_percentages_are_rejected(self):
        for bad in (0, -1, 101):
            with self.assertRaises(SizingError):
                size_trade(symbol="BTC", side="long", entry=80_000, stop_loss=78_400,
                           risk_pct=bad, **ACCOUNT)

    def test_summary_mentions_liquidation(self):
        trade = size_trade(symbol="BTC", side="long", entry=80_000, stop_loss=78_400,
                           take_profit=83_200, risk_pct=1.0, **ACCOUNT)
        text = trade.summary()
        self.assertIn("liquidation", text)
        self.assertIn("BTC", text)


if __name__ == "__main__":
    unittest.main()
