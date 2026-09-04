import unittest

from native_mt5.adapters.base import AdapterError
from native_mt5.adapters.mock import MockAdapter
from native_mt5.config import Config, ConfigError, TerminalCredentials
from native_mt5.safety import SafetyError, TradeMode
from native_mt5.session import Session


def session(mode=TradeMode.PAPER, **overrides):
    settings = {"adapter": "mock", "mode": mode, "max_order_volume": 1.0}
    settings.update(overrides)
    config = Config(**settings)
    return Session(config, adapter=MockAdapter(mode=mode)).open()


class StatusTests(unittest.TestCase):
    def test_status_names_the_mode_and_never_leaks_the_password(self):
        s = session(TradeMode.READONLY)
        status = s.status()
        self.assertEqual(status["mode"], "readonly")
        self.assertTrue(status["connected"])
        self.assertNotIn("password", repr(status).lower())

    def test_config_describe_omits_credentials(self):
        config = Config(
            credentials=TerminalCredentials(login=1, password="hunter2", server="X")
        )
        self.assertNotIn("hunter2", repr(config.describe()))


class MarketDataTests(unittest.TestCase):
    def setUp(self):
        self.s = session()

    def test_account_reports_balance_and_equity(self):
        account = self.s.account()
        self.assertEqual(account["currency"], "USD")
        self.assertGreater(account["balance"], 0)

    def test_symbol_search_narrows_the_list(self):
        self.assertGreater(self.s.list_symbols()["count"], 1)
        self.assertEqual(self.s.list_symbols("XAU")["count"], 1)

    def test_unknown_symbol_says_what_is_available(self):
        with self.assertRaises(AdapterError) as ctx:
            self.s.quote("NOTREAL")
        self.assertIn("EURUSD", str(ctx.exception))

    def test_quote_has_a_positive_spread(self):
        quote = self.s.quote("eurusd")
        self.assertGreater(quote["ask"], quote["bid"])
        self.assertGreater(quote["spread_points"], 0)

    def test_candles_are_deterministic_across_calls(self):
        first = self.s.candles("EURUSD", "H1", 20)
        second = self.s.candles("EURUSD", "H1", 20)
        self.assertEqual(first["candles"], second["candles"])
        self.assertEqual(first["count"], 20)

    def test_candle_highs_and_lows_bracket_the_body(self):
        for bar in self.s.candles("XAUUSD", "M15", 50)["candles"]:
            self.assertGreaterEqual(bar["high"], max(bar["open"], bar["close"]))
            self.assertLessEqual(bar["low"], min(bar["open"], bar["close"]))

    def test_unknown_timeframe_is_rejected(self):
        with self.assertRaises(AdapterError):
            self.s.candles("EURUSD", "H3", 10)


class SizingTests(unittest.TestCase):
    def test_risk_pct_is_clamped_to_the_server_ceiling(self):
        s = session(max_risk_per_trade_pct=1.0)
        sized = s.size_position("EURUSD", "buy", 1.08500, 1.08300, risk_pct=50.0)
        self.assertIn("risk_pct_note", sized)
        self.assertEqual(sized["risk_pct"], 1.0)


class TradingTests(unittest.TestCase):
    def test_readonly_refuses_orders_and_closes(self):
        s = session(TradeMode.READONLY)
        with self.assertRaises(SafetyError):
            s.place_order("EURUSD", "buy", 0.1)
        with self.assertRaises(SafetyError):
            s.close_position(1)

    def test_preview_is_safe_in_readonly_and_explains_the_block(self):
        s = session(TradeMode.READONLY)
        preview = s.preview_order("EURUSD", "buy", 0.1, stop_loss=1.0)
        self.assertFalse(preview["would_be_accepted"])
        self.assertIn("readonly", preview["blocked_by"])
        self.assertEqual(s.positions()["count"], 0)

    def test_preview_warns_when_there_is_no_stop(self):
        preview = session().preview_order("EURUSD", "buy", 0.1)
        self.assertIn("warning", preview)
        self.assertIsNone(preview["risk_at_stop"])

    def test_paper_round_trip_opens_then_closes(self):
        s = session()
        opened = s.place_order("EURUSD", "buy", 0.1)
        self.assertTrue(opened["ok"])
        self.assertTrue(opened["simulated"])
        self.assertEqual(s.positions()["count"], 1)

        closed = s.close_position(opened["ticket"])
        self.assertTrue(closed["ok"])
        self.assertEqual(s.positions()["count"], 0)
        self.assertEqual(s.history(1)["count"], 1)

    def test_performance_summarises_the_paper_history(self):
        s = session()
        ticket = s.place_order("XAUUSD", "buy", 0.1)["ticket"]
        s.close_position(ticket)
        self.assertEqual(s.performance(1)["trades"], 1)

    def test_closing_an_unknown_ticket_is_an_adapter_error(self):
        with self.assertRaises(AdapterError):
            session().close_position(999)

    def test_volume_cap_blocks_the_order_before_the_adapter_sees_it(self):
        s = session(max_order_volume=0.5)
        with self.assertRaises(SafetyError):
            s.place_order("EURUSD", "buy", 2.0)
        self.assertEqual(s.positions()["count"], 0)

    def test_position_cap_blocks_the_next_order(self):
        s = session(max_open_positions=1)
        s.place_order("EURUSD", "buy", 0.1)
        with self.assertRaises(SafetyError):
            s.place_order("GBPUSD", "buy", 0.1)


class LiveModeTests(unittest.TestCase):
    """Live mode is exercised against the mock adapter via a direct Session."""

    def setUp(self):
        config = Config(adapter="terminal", mode=TradeMode.LIVE, max_order_volume=1.0)
        self.s = Session(config, adapter=MockAdapter(mode=TradeMode.LIVE)).open()

    def test_order_without_a_token_is_refused(self):
        with self.assertRaises(SafetyError) as ctx:
            self.s.place_order("EURUSD", "buy", 0.1)
        self.assertIn("preview_order", str(ctx.exception))

    def test_preview_hands_back_a_token_that_works(self):
        preview = self.s.preview_order("EURUSD", "buy", 0.1, stop_loss=1.0)
        token = preview["confirmation_token"]
        result = self.s.place_order("EURUSD", "buy", 0.1, stop_loss=1.0, confirm_token=token)
        self.assertTrue(result["ok"])

    def test_a_token_for_a_smaller_order_does_not_authorise_a_bigger_one(self):
        token = self.s.preview_order("EURUSD", "buy", 0.1)["confirmation_token"]
        with self.assertRaises(SafetyError):
            self.s.place_order("EURUSD", "buy", 1.0, confirm_token=token)


class ConfigTests(unittest.TestCase):
    def test_live_against_the_mock_adapter_is_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            Config(adapter="mock", mode=TradeMode.LIVE).validate()
        self.assertIn("meaningless", str(ctx.exception))

    def test_out_of_range_caps_are_rejected(self):
        with self.assertRaises(ConfigError):
            Config(max_risk_per_trade_pct=0).validate()
        with self.assertRaises(ConfigError):
            Config(max_order_volume=0).validate()

    def test_defaults_are_readonly_and_mock(self):
        config = Config()
        config.validate()
        self.assertEqual(config.adapter, "mock")
        self.assertIs(config.mode, TradeMode.READONLY)


if __name__ == "__main__":
    unittest.main()
