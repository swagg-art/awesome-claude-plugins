import sys, pathlib, datetime as dt
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from fake_mt5 import FakeMT5
from tbot.live import MT5Broker, BrokerError, RiskGuard, GuardConfig, GuardTripped

def check(name, fn):
    try:
        fn(); print(f"  PASS  {name}")
    except AssertionError as e:
        print(f"  FAIL  {name}: {e}"); raise

def t_live_account_refused():
    b = MT5Broker(mt5=FakeMT5(demo=False), dry_run=False, allow_live=False)
    try:
        b.connect(); assert False, "connected to a LIVE account"
    except BrokerError as e:
        assert "NOT a demo" in str(e), e
        assert b.mt5.shutdown_called, "must disconnect after refusing"

def t_demo_ok():
    b = MT5Broker(mt5=FakeMT5(demo=True)); b.connect(); assert b.connected

def t_algo_disabled_refused():
    b = MT5Broker(mt5=FakeMT5(trade_allowed=False))
    try:
        b.connect(); assert False, "connected with algo trading off"
    except BrokerError as e:
        assert "Algo trading is disabled" in str(e)

def t_dry_run_sends_nothing():
    m = FakeMT5(); b = MT5Broker(mt5=m, dry_run=True); b.connect()
    r = b.place_market_order("EURUSD","BUY",0.10, sl_price=1.09, tp_price=1.12)
    assert r.dry_run and r.ok and not m.sent, "dry run must not send"

def t_rejection_detected():
    """THE bug: retcode 10019 (no money) must read as failure, not success."""
    m = FakeMT5(retcode=10019); b = MT5Broker(mt5=m, dry_run=False); b.connect()
    r = b.place_market_order("EURUSD","BUY",0.10, sl_price=1.09)
    assert not r.ok, "10019 reported as SUCCESS - this is the original bug"
    assert r.meaning == "insufficient funds", r.meaning
    # and the naive check would have passed:
    assert bool(m.sent[0] and 10019), "demonstrates truthiness of any retcode"

def t_success_detected():
    m = FakeMT5(retcode=10009); b = MT5Broker(mt5=m, dry_run=False); b.connect()
    r = b.place_market_order("EURUSD","BUY",0.10, sl_price=1.09)
    assert r.ok and r.order == 777

def t_volume_normalised():
    b = MT5Broker(mt5=FakeMT5()); b.connect()
    assert b.normalize_volume("EURUSD", 0.007) == 0.0, "below min must be zero"
    assert b.normalize_volume("EURUSD", 0.1234) <= 0.1234, "must never round UP"
    assert b.normalize_volume("EURUSD", 999) == 50.0, "must clamp to max"

def t_filling_negotiated():
    from fake_mt5 import ORDER_FILLING_IOC, ORDER_FILLING_FOK, ORDER_FILLING_RETURN
    assert MT5Broker(mt5=FakeMT5(filling_mask=2)).pick_filling_mode("E") == ORDER_FILLING_IOC
    assert MT5Broker(mt5=FakeMT5(filling_mask=1)).pick_filling_mode("E") == ORDER_FILLING_FOK
    assert MT5Broker(mt5=FakeMT5(filling_mask=0)).pick_filling_mode("E") == ORDER_FILLING_RETURN

def t_bad_stops_rejected():
    b = MT5Broker(mt5=FakeMT5(), dry_run=True); b.connect()
    for side, sl in (("BUY", 1.20), ("SELL", 1.00)):
        try:
            b.place_market_order("EURUSD", side, 0.1, sl_price=sl)
            assert False, f"accepted {side} stop on the wrong side of price"
        except BrokerError:
            pass

def t_guards():
    g = RiskGuard(GuardConfig(max_daily_loss_pct=0.03, max_open_positions=1,
                              min_seconds_between_orders=5))
    now = dt.datetime(2026,8,29,10,0)
    g.check(now=now, equity=10_000, open_positions=0, monotonic=100.0)
    g.record_order(100.0)
    try:
        g.check(now=now, equity=10_000, open_positions=0, monotonic=102.0)
        assert False, "throttle not enforced"
    except GuardTripped as e: assert "throttled" in str(e)
    try:
        g.check(now=now, equity=9_600, open_positions=0, monotonic=200.0)
        assert False, "daily loss cap not enforced"
    except GuardTripped as e: assert "daily loss" in str(e)
    try:
        g.check(now=now, equity=10_000, open_positions=1, monotonic=200.0)
        assert False, "position cap not enforced"
    except GuardTripped as e: assert "position" in str(e)
    for _ in range(4): g.record_result(-10)
    try:
        g.check(now=now, equity=10_000, open_positions=0, monotonic=300.0)
        assert False, "consecutive-loss halt not enforced"
    except GuardTripped as e: assert "consecutive losses" in str(e)
    g.record_result(+50); assert g.consecutive_losses == 0

def t_no_async_api():
    """Prove order_send_async is not part of the package surface."""
    m = FakeMT5()
    assert not hasattr(m, "order_send_async")

print("MT5 execution layer")
for name, fn in [
    ("refuses a live account", t_live_account_refused),
    ("accepts a demo account", t_demo_ok),
    ("refuses when algo trading is off", t_algo_disabled_refused),
    ("dry run sends nothing", t_dry_run_sends_nothing),
    ("detects rejection (retcode 10019)", t_rejection_detected),
    ("detects success (retcode 10009)", t_success_detected),
    ("normalises volume to the symbol grid", t_volume_normalised),
    ("negotiates filling mode", t_filling_negotiated),
    ("rejects stops on the wrong side", t_bad_stops_rejected),
    ("guards trip correctly", t_guards),
    ("order_send_async does not exist", t_no_async_api),
]:
    check(name, fn)
print("\nall passed")
