"""A MetaTrader5-shaped stub. Records what was sent; returns what you set up."""

from __future__ import annotations


class Record:
    """Stands in for MT5's namedtuples, which expose _asdict()."""

    def __init__(self, **fields):
        self.__dict__.update(fields)

    def _asdict(self) -> dict:
        return dict(self.__dict__)


def symbol(
    name="EURUSD",
    digits=5,
    point=0.00001,
    volume_min=0.01,
    volume_max=100.0,
    volume_step=0.01,
    filling_mode=2,
    trade_stops_level=0,
    visible=True,
    trade_tick_value=1.0,
    trade_tick_size=0.00001,
):
    return Record(
        name=name,
        digits=digits,
        point=point,
        volume_min=volume_min,
        volume_max=volume_max,
        volume_step=volume_step,
        filling_mode=filling_mode,
        trade_stops_level=trade_stops_level,
        visible=visible,
        trade_tick_value=trade_tick_value,
        trade_tick_size=trade_tick_size,
    )


def position(ticket=1, sym="EURUSD", type_=0, volume=0.10, price_open=1.0850, sl=0.0, tp=0.0):
    return Record(
        ticket=ticket,
        symbol=sym,
        type=type_,
        volume=volume,
        price_open=price_open,
        price_current=price_open,
        sl=sl,
        tp=tp,
        profit=0.0,
    )


class StubMT5:
    def __init__(self, symbols=None, bid=1.08400, ask=1.08420):
        self.symbols = symbols or [symbol()]
        self.bid, self.ask = bid, ask
        self.sent: list = []
        self.retcodes: list = []          # queued retcodes, one per order_send
        self.positions: list = []
        self.orders: list = []
        self.deals: list = []
        self.rates = None
        self.initialized = False
        self.shutdown_called = False
        self.error = (0, "ok")
        self.account_data = {
            "login": 123456,
            "server": "BrokerX-Demo",
            "currency": "USD",
            "balance": 10000.0,
            "equity": 10000.0,
            "profit": 0.0,
            "margin": 0.0,
            "margin_free": 10000.0,
            "margin_level": 0.0,
            "leverage": 500,
            "trade_mode": 0,
        }

    # -- lifecycle
    def initialize(self, **kwargs):
        self.init_kwargs = kwargs
        self.initialized = True
        return True

    def shutdown(self):
        self.shutdown_called = True

    def last_error(self):
        return self.error

    # -- data
    def account_info(self):
        return Record(**self.account_data)

    def symbols_get(self):
        return list(self.symbols)

    def symbol_info(self, name):
        for s in self.symbols:
            if s.name == name:
                return s
        return None

    def symbol_info_tick(self, name):
        return Record(bid=self.bid, ask=self.ask)

    def symbol_select(self, name, enable):
        return True

    def positions_get(self, symbol=None, ticket=None):
        found = self.positions
        if ticket is not None:
            found = [p for p in found if p.ticket == ticket]
        if symbol is not None:
            found = [p for p in found if p.symbol == symbol]
        return tuple(found)

    def orders_get(self):
        return tuple(self.orders)

    def copy_rates_from_pos(self, name, timeframe, start, count):
        return self.rates

    def history_deals_get(self, start, end):
        return tuple(self.deals)

    # -- trading
    def order_send(self, request):
        self.sent.append(dict(request))
        retcode = self.retcodes.pop(0) if self.retcodes else 10009
        return Record(
            retcode=retcode,
            order=555000 + len(self.sent),
            deal=666000 + len(self.sent),
            volume=request.get("volume", 0),
            price=request.get("price", 0),
            comment="stub",
        )
