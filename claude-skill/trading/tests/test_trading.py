#!/usr/bin/env python3
"""Tests for the MT5 trading skill. Stdlib only, no terminal:

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import backtest as bt  # noqa: E402
import journal as jr  # noqa: E402
import mt5_client as mc  # noqa: E402
import risk as rk  # noqa: E402
import tables  # noqa: E402
from stub_mt5 import StubMT5, position, symbol  # noqa: E402


def client(stub=None, **config_kwargs) -> mc.MT5:
    stub = stub or StubMT5()
    mc.set_backend(stub)
    session = mc.MT5(mc.Config(**config_kwargs))
    session.connect()
    session.stub = stub
    return session


class SymbolResolutionTests(unittest.TestCase):
    def test_exact_match(self):
        mt = client()
        self.assertEqual(mt.resolve_symbol("eurusd"), "EURUSD")

    def test_broker_suffix_is_found(self):
        mt = client(StubMT5(symbols=[symbol(name="EURUSD.raw")]))
        self.assertEqual(mt.resolve_symbol("EURUSD"), "EURUSD.raw")

    def test_ambiguous_prefix_is_reported(self):
        stub = StubMT5(symbols=[symbol(name="EURUSD.raw"), symbol(name="EURUSDm")])
        with self.assertRaises(mc.MT5Error) as ctx:
            client(stub).resolve_symbol("EURUSD")
        self.assertIn("ambiguous", str(ctx.exception))

    def test_unknown_symbol(self):
        with self.assertRaises(mc.MT5Error) as ctx:
            client().resolve_symbol("NOPE")
        self.assertIn("unknown symbol", str(ctx.exception))


class VolumeTests(unittest.TestCase):
    def test_rounds_to_broker_step(self):
        mt = client()
        info = mt.symbol("EURUSD")
        self.assertEqual(mt.normalize_volume(info, 0.1234), 0.12)

    def test_below_minimum_rejected(self):
        mt = client()
        with self.assertRaises(mc.MT5Error) as ctx:
            mt.normalize_volume(mt.symbol("EURUSD"), 0.001)
        self.assertIn("minimum", str(ctx.exception))

    def test_above_symbol_maximum_rejected(self):
        mt = client()
        with self.assertRaises(mc.MT5Error):
            mt.normalize_volume(mt.symbol("EURUSD"), 500)

    def test_config_cap_rejected(self):
        mt = client(max_volume=0.5)
        with self.assertRaises(mc.MT5Error) as ctx:
            mt.normalize_volume(mt.symbol("EURUSD"), 1.0)
        self.assertIn("max_volume", str(ctx.exception))


class FillingModeTests(unittest.TestCase):
    def test_prefers_ioc(self):
        mt = client(StubMT5(symbols=[symbol(filling_mode=3)]))
        self.assertEqual(mt.filling_mode(mt.symbol("EURUSD")), mc.ORDER_FILLING_IOC)

    def test_falls_back_to_fok(self):
        mt = client(StubMT5(symbols=[symbol(filling_mode=1)]))
        self.assertEqual(mt.filling_mode(mt.symbol("EURUSD")), mc.ORDER_FILLING_FOK)

    def test_falls_back_to_return(self):
        mt = client(StubMT5(symbols=[symbol(filling_mode=0)]))
        self.assertEqual(mt.filling_mode(mt.symbol("EURUSD")), mc.ORDER_FILLING_RETURN)


class StopValidationTests(unittest.TestCase):
    def setUp(self):
        self.mt = client()
        self.info = self.mt.symbol("EURUSD")

    def test_buy_stop_must_be_below_entry(self):
        with self.assertRaises(mc.MT5Error):
            self.mt.check_stops(self.info, "buy", 1.0850, 1.0900, None)

    def test_sell_stop_must_be_above_entry(self):
        with self.assertRaises(mc.MT5Error):
            self.mt.check_stops(self.info, "sell", 1.0850, 1.0800, None)

    def test_buy_target_must_be_above_entry(self):
        with self.assertRaises(mc.MT5Error):
            self.mt.check_stops(self.info, "buy", 1.0850, None, 1.0800)

    def test_respects_broker_stop_level(self):
        mt = client(StubMT5(symbols=[symbol(trade_stops_level=100)]))  # 100 points = 0.001
        info = mt.symbol("EURUSD")
        with self.assertRaises(mc.MT5Error) as ctx:
            mt.check_stops(info, "buy", 1.0850, 1.08450, None)
        self.assertIn("requires at least", str(ctx.exception))

    def test_valid_stops_pass(self):
        self.assertIsNone(self.mt.check_stops(self.info, "buy", 1.0850, 1.0820, 1.0900))


class MarketOrderTests(unittest.TestCase):
    def test_buy_builds_correct_request(self):
        mt = client()
        mt.market_order("EURUSD", "buy", 0.10, sl=1.0820, tp=1.0900)
        sent = mt.stub.sent[0]
        self.assertEqual(sent["action"], mc.TRADE_ACTION_DEAL)
        self.assertEqual(sent["type"], mc.ORDER_TYPE_BUY)
        self.assertEqual(sent["price"], mt.stub.ask)  # buys lift the ask
        self.assertEqual(sent["volume"], 0.10)
        self.assertEqual(sent["sl"], 1.0820)
        self.assertEqual(sent["tp"], 1.0900)
        self.assertEqual(sent["type_filling"], mc.ORDER_FILLING_IOC)

    def test_sell_uses_the_bid(self):
        mt = client()
        mt.market_order("EURUSD", "sell", 0.10)
        self.assertEqual(mt.stub.sent[0]["price"], mt.stub.bid)
        self.assertEqual(mt.stub.sent[0]["type"], mc.ORDER_TYPE_SELL)

    def test_no_stops_means_no_sl_tp_keys(self):
        mt = client()
        mt.market_order("EURUSD", "buy", 0.10)
        self.assertNotIn("sl", mt.stub.sent[0])
        self.assertNotIn("tp", mt.stub.sent[0])

    def test_bad_side_rejected(self):
        with self.assertRaises(mc.MT5Error):
            client().market_order("EURUSD", "long", 0.10)

    def test_dry_run_sends_nothing(self):
        mt = client(dry_run=True)
        result = mt.market_order("EURUSD", "buy", 0.10)
        self.assertTrue(result["dry_run"])
        self.assertEqual(mt.stub.sent, [])

    def test_symbol_not_in_allowlist(self):
        mt = client(allowed_symbols=["XAUUSD"])
        with self.assertRaises(mc.MT5Error) as ctx:
            mt.market_order("EURUSD", "buy", 0.10)
        self.assertIn("allowed_symbols", str(ctx.exception))
        self.assertEqual(mt.stub.sent, [])

    def test_comment_is_truncated_for_mt5(self):
        mt = client()
        mt.market_order("EURUSD", "buy", 0.10, comment="x" * 60)
        self.assertLessEqual(len(mt.stub.sent[0]["comment"]), 31)


class RetcodeTests(unittest.TestCase):
    def test_requote_is_retried_with_a_fresh_price(self):
        stub = StubMT5()
        stub.retcodes = [10004, 10009]
        mt = client(stub)
        result = mt.market_order("EURUSD", "buy", 0.10)
        self.assertEqual(result["retcode"], mc.TRADE_RETCODE_DONE)
        self.assertEqual(len(stub.sent), 2)

    def test_hard_rejection_raises_with_a_readable_reason(self):
        stub = StubMT5()
        stub.retcodes = [10019]
        with self.assertRaises(mc.OrderRejected) as ctx:
            client(stub).market_order("EURUSD", "buy", 0.10)
        self.assertIn("not enough money", str(ctx.exception))
        self.assertEqual(ctx.exception.retcode, 10019)

    def test_unsupported_filling_mode_is_explained(self):
        stub = StubMT5()
        stub.retcodes = [10030]
        with self.assertRaises(mc.OrderRejected) as ctx:
            client(stub).market_order("EURUSD", "buy", 0.10)
        self.assertIn("filling mode", str(ctx.exception))

    def test_persistent_requote_eventually_raises(self):
        stub = StubMT5()
        stub.retcodes = [10004, 10004, 10004]
        with self.assertRaises(mc.OrderRejected):
            client(stub).market_order("EURUSD", "buy", 0.10)


class PendingOrderTests(unittest.TestCase):
    def test_buy_limit_below_market_is_accepted(self):
        mt = client()
        mt.pending_order("EURUSD", "buy", "limit", 0.10, 1.0800)
        self.assertEqual(mt.stub.sent[0]["type"], mc.ORDER_TYPE_BUY_LIMIT)
        self.assertEqual(mt.stub.sent[0]["action"], mc.TRADE_ACTION_PENDING)

    def test_buy_limit_above_market_is_rejected(self):
        with self.assertRaises(mc.MT5Error) as ctx:
            client().pending_order("EURUSD", "buy", "limit", 0.10, 1.0900)
        self.assertIn("must be below the market", str(ctx.exception))

    def test_buy_stop_below_market_is_rejected(self):
        with self.assertRaises(mc.MT5Error):
            client().pending_order("EURUSD", "buy", "stop", 0.10, 1.0800)

    def test_sell_stop_above_market_is_rejected(self):
        with self.assertRaises(mc.MT5Error):
            client().pending_order("EURUSD", "sell", "stop", 0.10, 1.0900)

    def test_bad_combination(self):
        with self.assertRaises(mc.MT5Error):
            client().pending_order("EURUSD", "buy", "market", 0.10, 1.08)


class PositionTests(unittest.TestCase):
    def test_close_sends_the_opposite_side_against_the_ticket(self):
        stub = StubMT5()
        stub.positions = [position(ticket=42, type_=mc.ORDER_TYPE_BUY, volume=0.20)]
        mt = client(stub)
        mt.close_position(42)
        sent = stub.sent[0]
        self.assertEqual(sent["type"], mc.ORDER_TYPE_SELL)
        self.assertEqual(sent["position"], 42)
        self.assertEqual(sent["volume"], 0.20)
        self.assertEqual(sent["price"], stub.bid)

    def test_partial_close(self):
        stub = StubMT5()
        stub.positions = [position(ticket=42, volume=0.20)]
        client(stub).close_position(42, 0.05)
        self.assertEqual(stub.sent[0]["volume"], 0.05)

    def test_cannot_close_more_than_held(self):
        stub = StubMT5()
        stub.positions = [position(ticket=42, volume=0.10)]
        with self.assertRaises(mc.MT5Error) as ctx:
            client(stub).close_position(42, 0.50)
        self.assertIn("holds", str(ctx.exception))

    def test_unknown_ticket(self):
        with self.assertRaises(mc.MT5Error):
            client().close_position(999)

    def test_set_sltp_builds_an_sltp_action(self):
        stub = StubMT5()
        stub.positions = [position(ticket=7, price_open=1.0850)]
        mt = client(stub)
        mt.set_sltp(7, sl=1.0820, tp=1.0900)
        sent = stub.sent[0]
        self.assertEqual(sent["action"], mc.TRADE_ACTION_SLTP)
        self.assertEqual(sent["position"], 7)
        self.assertEqual(sent["sl"], 1.0820)

    def test_set_sltp_validates_direction(self):
        stub = StubMT5()
        stub.positions = [position(ticket=7, type_=mc.ORDER_TYPE_BUY, price_open=1.0850)]
        with self.assertRaises(mc.MT5Error):
            client(stub).set_sltp(7, sl=1.0900)

    def test_close_all(self):
        stub = StubMT5()
        stub.positions = [position(ticket=1), position(ticket=2)]
        results = client(stub).close_all()
        self.assertEqual(len(results), 2)
        self.assertEqual(len(stub.sent), 2)


class AccountAndBarsTests(unittest.TestCase):
    def test_demo_account_is_flagged(self):
        self.assertTrue(client().account()["is_demo"])

    def test_live_account_is_flagged(self):
        stub = StubMT5()
        stub.account_data.update(server="BrokerX-Live", trade_mode=2)
        self.assertFalse(client(stub).account()["is_demo"])

    def test_unknown_timeframe(self):
        with self.assertRaises(mc.MT5Error) as ctx:
            client().bars("EURUSD", "H3")
        self.assertIn("unknown timeframe", str(ctx.exception))

    def test_no_bars_returned(self):
        with self.assertRaises(mc.MT5Error):
            client().bars("EURUSD", "H1")

    def test_no_quotes_means_market_closed(self):
        stub = StubMT5(bid=0, ask=0)
        with self.assertRaises(mc.MT5Error) as ctx:
            client(stub).tick("EURUSD")
        self.assertIn("market may be closed", str(ctx.exception))


class RiskTests(unittest.TestCase):
    def test_sizing_math(self):
        s = rk.size_position(
            balance=10000, risk_pct=1, entry=1.0850, stop=1.0820,
            tick_value=1.0, tick_size=0.00001,
        )
        self.assertEqual(s.lots, 0.33)          # 0.3333 rounded down to the step
        self.assertEqual(s.risk_amount, 100.0)
        self.assertAlmostEqual(s.loss_at_stop, 99.0, places=6)

    def test_rounds_down_never_up(self):
        s = rk.size_position(
            balance=10000, risk_pct=1, entry=1.0850, stop=1.0820,
            tick_value=1.0, tick_size=0.00001,
        )
        self.assertLessEqual(s.loss_at_stop, s.risk_amount)

    def test_config_cap_applies(self):
        s = rk.size_position(
            balance=100000, risk_pct=2, entry=1.0850, stop=1.0840,
            tick_value=1.0, tick_size=0.00001, max_volume=1.0,
        )
        self.assertEqual(s.lots, 1.0)
        self.assertIn("max_volume", s.capped_by)

    def test_stop_too_wide_for_the_minimum_lot(self):
        with self.assertRaises(rk.RiskError) as ctx:
            rk.size_position(
                balance=100, risk_pct=0.5, entry=1.0850, stop=1.0000,
                tick_value=1.0, tick_size=0.00001,
            )
        self.assertIn("below the", str(ctx.exception))

    def test_zero_distance_rejected(self):
        with self.assertRaises(rk.RiskError):
            rk.size_position(10000, 1, 1.085, 1.085, 1.0, 0.00001)

    def test_bad_risk_pct(self):
        for pct in (0, -1, 101):
            with self.assertRaises(rk.RiskError):
                rk.size_position(10000, pct, 1.085, 1.082, 1.0, 0.00001)

    def test_r_multiple(self):
        self.assertAlmostEqual(rk.r_multiple(1.0850, 1.0820, 1.0910, "buy"), 2.0)
        self.assertAlmostEqual(rk.r_multiple(1.0850, 1.0880, 1.0790, "sell"), 2.0)
        self.assertAlmostEqual(rk.r_multiple(1.0850, 1.0820, 1.0820, "buy"), -1.0)

    def test_portfolio_heat(self):
        positions = [
            {"symbol": "EURUSD", "volume": 0.10, "price_open": 1.0850, "sl": 1.0820},
            {"symbol": "EURUSD", "volume": 0.10, "price_open": 1.0860, "sl": 0.0},
        ]
        heat = rk.portfolio_heat(positions, 10000, lambda s: 100000.0)
        self.assertAlmostEqual(heat["risk_amount"], 30.0, places=6)
        self.assertAlmostEqual(heat["heat_pct"], 0.30, places=6)
        self.assertEqual(heat["without_stop"], 1)
        self.assertEqual(heat["without_stop_symbols"], ["EURUSD"])


def deal(pid, entry, type_, price, profit=0.0, time=1000, volume=0.1, commission=0.0, swap=0.0):
    return {
        "position_id": pid, "entry": entry, "type": type_, "price": price,
        "profit": profit, "time": time, "volume": volume, "symbol": "EURUSD",
        "commission": commission, "swap": swap,
    }


class JournalTests(unittest.TestCase):
    def test_deals_fold_into_round_trips(self):
        deals = [
            deal(1, 0, 0, 1.0850, time=1000),
            deal(1, 1, 1, 1.0900, profit=50.0, time=4600),
        ]
        trades = jr.trades_from_deals(deals)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["side"], "buy")
        self.assertEqual(trades[0]["net"], 50.0)
        self.assertEqual(trades[0]["duration_min"], 60.0)

    def test_partial_exits_are_summed(self):
        deals = [
            deal(2, 0, 0, 1.0850, volume=0.2, time=1000),
            deal(2, 1, 1, 1.0880, profit=30.0, volume=0.1, time=2000),
            deal(2, 1, 1, 1.0890, profit=40.0, volume=0.1, time=3000),
        ]
        trades = jr.trades_from_deals(deals)
        self.assertEqual(trades[0]["partial_exits"], 2)
        self.assertEqual(trades[0]["profit"], 70.0)
        self.assertEqual(trades[0]["exit_price"], 1.0890)

    def test_costs_reduce_net(self):
        deals = [
            deal(3, 0, 0, 1.0850, commission=-2.0),
            deal(3, 1, 1, 1.0900, profit=50.0, commission=-2.0, swap=-1.0),
        ]
        trades = jr.trades_from_deals(deals)
        self.assertEqual(trades[0]["profit"], 50.0)
        self.assertEqual(trades[0]["net"], 45.0)

    def test_still_open_position_is_skipped(self):
        self.assertEqual(jr.trades_from_deals([deal(4, 0, 0, 1.0850)]), [])

    def test_stats(self):
        trades = [
            {"symbol": "EURUSD", "net": 100.0, "closed_at": "a"},
            {"symbol": "EURUSD", "net": -50.0, "closed_at": "b"},
            {"symbol": "XAUUSD", "net": 200.0, "closed_at": "c"},
            {"symbol": "XAUUSD", "net": -50.0, "closed_at": "d"},
        ]
        s = jr.stats(trades)
        self.assertEqual(s["trades"], 4)
        self.assertEqual(s["win_rate"], 0.5)
        self.assertEqual(s["net"], 200.0)
        self.assertEqual(s["profit_factor"], 3.0)
        self.assertEqual(s["expectancy"], 50.0)
        self.assertEqual(s["largest_loss"], -50.0)

    def test_max_drawdown(self):
        self.assertEqual(jr.max_drawdown([100, 150, 90, 200]), 60)
        self.assertEqual(jr.max_drawdown([10, 20, 30]), 0)

    def test_empty_journal(self):
        self.assertEqual(jr.stats([]), {"trades": 0})

    def test_merge_keeps_local_notes(self):
        existing = [{"position_id": 1, "net": 10.0, "closed_at": "a", "note": "kept", "setup": "s"}]
        incoming = [{"position_id": 1, "net": 12.0, "closed_at": "a"}]
        merged = jr.merge(existing, incoming)
        self.assertEqual(merged[0]["net"], 12.0)     # broker facts win
        self.assertEqual(merged[0]["note"], "kept")  # my notes survive

    def test_round_trip_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "j.jsonl")
            jr.save([{"position_id": 1, "net": 5.0, "closed_at": "a"}], path)
            self.assertEqual(jr.load(path)[0]["net"], 5.0)

    def test_annotate_unknown_trade(self):
        with self.assertRaises(jr.JournalError):
            jr.annotate([], 99, note="x")


def make_bars(closes):
    return [
        {"time": i, "open": c, "high": c + 0.5, "low": c - 0.5, "close": c, "volume": 1}
        for i, c in enumerate(closes)
    ]


class IndicatorTests(unittest.TestCase):
    def test_sma_warms_up_then_averages(self):
        self.assertEqual(bt.sma([1, 2, 3, 4, 5], 3), [None, None, 2.0, 3.0, 4.0])

    def test_rsi_of_a_pure_uptrend_is_100(self):
        values = bt.rsi([100 + i for i in range(30)], 14)
        self.assertEqual(values[-1], 100.0)

    def test_rsi_is_none_until_it_warms_up(self):
        self.assertIsNone(bt.rsi([100 + i for i in range(30)], 14)[13])

    def test_atr_is_positive(self):
        bars = make_bars([100 + i * 0.5 for i in range(40)])
        self.assertGreater(bt.atr(bars, 14)[-1], 0)


class BacktestTests(unittest.TestCase):
    def test_fills_at_the_next_bar_open_not_the_signal_bar(self):
        closes = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        bars = make_bars(closes)
        result = bt.run(bars, bt.ma_cross(2, 3))
        for trade in result.trades:
            self.assertGreater(trade.entry_index, 0)
            self.assertEqual(trade.entry_price, bars[trade.entry_index]["open"])

    def test_long_only_takes_no_shorts(self):
        bars = make_bars([10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 2, 3])
        result = bt.run(bars, bt.ma_cross(2, 3), allow_short=False)
        self.assertTrue(all(t.side == "buy" for t in result.trades))

    def test_stop_is_hit_intrabar(self):
        bars = make_bars([10] * 5)
        bars[3]["low"] = 5.0  # a spike down through any sensible stop
        result = bt.run(bars, lambda i, b, c: "buy" if i == 1 else None, stop_points=1.0)
        self.assertIn("stop", [t.reason for t in result.trades])

    def test_open_trade_is_closed_at_the_end_of_data(self):
        bars = make_bars([1, 2, 3, 4, 5, 6])
        result = bt.run(bars, lambda i, b, c: "buy" if i == 1 else None)
        self.assertEqual(result.trades[-1].reason, "end of data")
        self.assertIsNotNone(result.trades[-1].exit_price)

    def test_spread_costs_the_trade(self):
        bars = make_bars([1, 2, 3, 4, 5, 6])
        strategy = lambda i, b, c: "buy" if i == 1 else None  # noqa: E731
        free = bt.run(bars, strategy).stats()["net_points"]
        costed = bt.run(bars, strategy, spread=0.4).stats()["net_points"]
        self.assertLess(costed, free)

    def test_too_few_bars(self):
        with self.assertRaises(bt.BacktestError):
            bt.run(make_bars([1, 2]), bt.ma_cross())

    def test_missing_ohlc_is_rejected(self):
        with self.assertRaises(bt.BacktestError):
            bt.run([{"close": 1}] * 5, bt.ma_cross())

    def test_no_trades_reports_cleanly(self):
        result = bt.run(make_bars([1] * 60), lambda i, b, c: None)
        self.assertEqual(result.stats()["trades"], 0)

    def test_rates_conversion_from_tuples(self):
        bars = bt.bars_from_rates([(1700000000, 1.08, 1.09, 1.07, 1.085, 42)])
        self.assertEqual(bars[0]["high"], 1.09)
        self.assertEqual(bars[0]["volume"], 42)


class TableTests(unittest.TestCase):
    def test_every_line_is_the_same_width(self):
        text = tables.render(["A", "Bee"], [["x", 1.0], ["yyyy", -2.5]])
        self.assertEqual(len({len(line) for line in text.splitlines()}), 1)

    def test_empty_table_still_aligns(self):
        text = tables.render(["Ticket", "Symbol"], [])
        self.assertEqual(len({len(line) for line in text.splitlines()}), 1)
        self.assertIn("(none)", text)

    def test_signed_and_money(self):
        self.assertEqual(tables.signed(12.5), "+12.50")
        self.assertEqual(tables.signed(-12.5), "-12.50")
        self.assertEqual(tables.money(-1234.5, "USD"), "-1,234.50 USD")


if __name__ == "__main__":
    unittest.main()
