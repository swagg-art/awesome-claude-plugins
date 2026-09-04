import unittest

from native_mt5.safety import (
    Guard,
    OrderIntent,
    SafetyError,
    TradeMode,
    confirmation_token,
)


def guard(mode=TradeMode.PAPER, **kwargs):
    defaults = dict(max_order_volume=1.0, max_open_positions=5, symbol_allowlist=())
    defaults.update(kwargs)
    return Guard(mode=mode, **defaults)


class TradeModeTests(unittest.TestCase):
    def test_parse_is_case_insensitive(self):
        self.assertIs(TradeMode.parse("LIVE"), TradeMode.LIVE)
        self.assertIs(TradeMode.parse(" paper "), TradeMode.PAPER)

    def test_unknown_mode_lists_the_valid_ones(self):
        with self.assertRaises(ValueError) as ctx:
            TradeMode.parse("yolo")
        self.assertIn("readonly", str(ctx.exception))

    def test_only_live_requires_confirmation(self):
        self.assertFalse(TradeMode.READONLY.allows_orders)
        self.assertTrue(TradeMode.PAPER.allows_orders)
        self.assertFalse(TradeMode.PAPER.requires_confirmation)
        self.assertTrue(TradeMode.LIVE.requires_confirmation)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.intent = OrderIntent("eurusd", "BUY", 0.1, stop_loss=1.08, take_profit=1.10)

    def test_readonly_refuses_every_order(self):
        with self.assertRaises(SafetyError) as ctx:
            guard(TradeMode.READONLY).check(self.intent, open_positions=0)
        self.assertIn("readonly", str(ctx.exception))

    def test_paper_accepts_a_sane_order(self):
        guard().check(self.intent, open_positions=0)

    def test_volume_cap_is_enforced(self):
        big = OrderIntent("EURUSD", "buy", 5.0)
        with self.assertRaises(SafetyError) as ctx:
            guard().check(big, open_positions=0)
        self.assertIn("exceeds the configured cap", str(ctx.exception))

    def test_position_count_cap_is_enforced(self):
        with self.assertRaises(SafetyError) as ctx:
            guard(max_open_positions=2).check(self.intent, open_positions=2)
        self.assertIn("cap", str(ctx.exception))

    def test_allowlist_blocks_other_symbols(self):
        with self.assertRaises(SafetyError) as ctx:
            guard(symbol_allowlist=("XAUUSD",)).check(self.intent, open_positions=0)
        self.assertIn("allowlist", str(ctx.exception))

    def test_allowlist_is_matched_case_insensitively(self):
        guard(symbol_allowlist=("EURUSD",)).check(self.intent, open_positions=0)

    def test_inverted_stops_are_rejected(self):
        inverted = OrderIntent("EURUSD", "buy", 0.1, stop_loss=1.10, take_profit=1.08)
        with self.assertRaises(SafetyError):
            guard().check(inverted, open_positions=0)

    def test_sell_stops_are_checked_the_other_way_round(self):
        good = OrderIntent("EURUSD", "sell", 0.1, stop_loss=1.10, take_profit=1.08)
        guard().check(good, open_positions=0)
        with self.assertRaises(SafetyError):
            guard().check(
                OrderIntent("EURUSD", "sell", 0.1, stop_loss=1.08, take_profit=1.10),
                open_positions=0,
            )

    def test_non_positive_volume_is_rejected(self):
        with self.assertRaises(SafetyError):
            guard().check(OrderIntent("EURUSD", "buy", 0.0), open_positions=0)

    def test_unknown_side_is_rejected(self):
        with self.assertRaises(SafetyError):
            guard().check(OrderIntent("EURUSD", "hold", 0.1), open_positions=0)


class ConfirmationTokenTests(unittest.TestCase):
    def test_live_order_without_a_token_is_refused(self):
        intent = OrderIntent("EURUSD", "buy", 0.1)
        with self.assertRaises(SafetyError) as ctx:
            guard(TradeMode.LIVE).check(intent, open_positions=0)
        self.assertIn("confirmation token", str(ctx.exception))

    def test_live_order_with_the_matching_token_passes(self):
        intent = OrderIntent("EURUSD", "buy", 0.1)
        guard(TradeMode.LIVE).check(
            intent, open_positions=0, token=confirmation_token(intent)
        )

    def test_token_does_not_transfer_to_a_different_order(self):
        previewed = OrderIntent("EURUSD", "buy", 0.1)
        executed = OrderIntent("EURUSD", "buy", 1.0)
        with self.assertRaises(SafetyError):
            guard(TradeMode.LIVE).check(
                executed, open_positions=0, token=confirmation_token(previewed)
            )

    def test_token_ignores_casing_and_whitespace(self):
        self.assertEqual(
            confirmation_token(OrderIntent(" eurusd ", "BUY", 0.1)),
            confirmation_token(OrderIntent("EURUSD", "buy", 0.1)),
        )


if __name__ == "__main__":
    unittest.main()
