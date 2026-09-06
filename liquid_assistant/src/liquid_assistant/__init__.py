"""Risk arithmetic for trading Liquid perpetuals with a human in the loop.

Liquid's own tools take a USD notional and a leverage. People think in "risk one
percent of my account". Converting between those two, correctly, is where perp
accounts die — so it lives here, in pure functions with tests, rather than in a
model's head.
"""

__version__ = "0.1.0"

from .funding import FundingEstimate, estimate_funding
from .review import review_portfolio
from .sizing import SizingError, Trade, size_trade

__all__ = [
    "FundingEstimate",
    "SizingError",
    "Trade",
    "estimate_funding",
    "review_portfolio",
    "size_trade",
]
