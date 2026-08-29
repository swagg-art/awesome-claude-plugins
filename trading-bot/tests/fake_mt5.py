"""Minimal MetaTrader5 stand-in for testing the broker off-Windows."""
from types import SimpleNamespace

TRADE_ACTION_DEAL = 1
ORDER_TYPE_BUY, ORDER_TYPE_SELL = 0, 1
ORDER_TIME_GTC = 0
ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN = 0, 1, 2
ACCOUNT_TRADE_MODE_DEMO, ACCOUNT_TRADE_MODE_REAL = 0, 2
SYMBOL_TRADE_MODE_DISABLED, SYMBOL_TRADE_MODE_FULL = 0, 4


class FakeMT5:
    def __init__(self, *, demo=True, filling_mask=2, retcode=10009,
                 trade_allowed=True, bid=1.10000, ask=1.10012):
        self.demo, self.filling_mask, self.retcode = demo, filling_mask, retcode
        self.trade_allowed, self.bid, self.ask = trade_allowed, bid, ask
        self.sent, self.checked, self.shutdown_called = [], [], False
        self._positions = []
        for k, v in globals().items():
            if k.isupper():
                setattr(self, k, v)

    def initialize(self, **kw): return True
    def shutdown(self): self.shutdown_called = True
    def last_error(self): return (1, "fake error")
    def terminal_info(self): return SimpleNamespace(trade_allowed=self.trade_allowed)

    def account_info(self):
        return SimpleNamespace(
            login=12345, server="Fake-Demo", balance=10_000.0, equity=10_000.0,
            currency="USD",
            trade_mode=ACCOUNT_TRADE_MODE_DEMO if self.demo else ACCOUNT_TRADE_MODE_REAL)

    def symbol_info(self, s):
        if s == "NOPE":
            return None
        return SimpleNamespace(visible=True, volume_min=0.01, volume_max=50.0,
                               volume_step=0.01, digits=5, point=0.00001,
                               filling_mode=self.filling_mask,
                               trade_mode=SYMBOL_TRADE_MODE_FULL)

    def symbol_select(self, s, on): return True
    def symbol_info_tick(self, s): return SimpleNamespace(bid=self.bid, ask=self.ask)
    def positions_get(self, symbol=None): return list(self._positions)

    def order_check(self, req):
        self.checked.append(req)
        return SimpleNamespace(retcode=0, comment="ok")

    def order_send(self, req):
        self.sent.append(req)
        return SimpleNamespace(retcode=self.retcode, order=777, deal=888,
                               price=req["price"], volume=req["volume"],
                               comment="done", request_id=42)
