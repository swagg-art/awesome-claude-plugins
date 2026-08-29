"""Instrument specifications.

The numbers in here decide whether a backtest is honest. Spread and
commission are not decoration - on short holding periods they are usually
larger than the edge being tested.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    symbol: str
    kind: str                    # "fx" | "crypto"
    pip_size: float              # price increment defining one pip (fx) or 1.0 (crypto)
    contract_size: float         # units per 1.0 lot (fx: 100_000); crypto: 1.0 (size in coins)
    quote_ccy: str
    typical_spread_pips: float   # round-trip cost is paid via spread on entry+exit
    commission_per_lot: float    # per side, in account currency
    funding_rate_daily: float    # crypto perp funding / fx swap, as a fraction of notional
    min_lot: float
    lot_step: float

    def pip_value_per_lot(self, price: float, usd_per_quote: float = 1.0) -> float:
        """Account-currency value of one pip for one lot.

        For a USD-quoted pair with a USD account this is exact.
        For anything else, pass usd_per_quote as the quote->account rate.
        """
        if self.kind == "crypto":
            return self.contract_size * self.pip_size * usd_per_quote
        return self.contract_size * self.pip_size * usd_per_quote

    def round_lot(self, lots: float) -> float:
        if lots < self.min_lot:
            return 0.0
        steps = int(lots / self.lot_step)
        return round(steps * self.lot_step, 8)


# Conservative defaults. Retail spreads, not institutional. Override with
# real numbers pulled from your own broker/exchange before trusting output.
EURUSD = Instrument(
    symbol="EURUSD", kind="fx", pip_size=0.0001, contract_size=100_000,
    quote_ccy="USD", typical_spread_pips=1.2, commission_per_lot=3.5,
    funding_rate_daily=0.0, min_lot=0.01, lot_step=0.01,
)

GBPUSD = Instrument(
    symbol="GBPUSD", kind="fx", pip_size=0.0001, contract_size=100_000,
    quote_ccy="USD", typical_spread_pips=1.6, commission_per_lot=3.5,
    funding_rate_daily=0.0, min_lot=0.01, lot_step=0.01,
)

BTCUSDT = Instrument(
    symbol="BTC/USDT", kind="crypto", pip_size=1.0, contract_size=1.0,
    quote_ccy="USDT", typical_spread_pips=2.0, commission_per_lot=0.0,
    funding_rate_daily=0.0003, min_lot=0.0001, lot_step=0.0001,
)

REGISTRY = {i.symbol: i for i in (EURUSD, GBPUSD, BTCUSDT)}
