"""Market adapters: one broker-agnostic interface, several backends."""

from .base import (
    Account,
    Adapter,
    AdapterError,
    Candle,
    Deal,
    OrderResult,
    Position,
    Quote,
    SymbolInfo,
)

__all__ = [
    "Account",
    "Adapter",
    "AdapterError",
    "Candle",
    "Deal",
    "OrderResult",
    "Position",
    "Quote",
    "SymbolInfo",
    "build_adapter",
]


def build_adapter(config) -> Adapter:
    """Instantiate the adapter named by the config.

    Imported lazily so that the mock path never needs the MetaTrader5 package,
    which only installs on Windows.
    """

    if config.adapter == "mock":
        from .mock import MockAdapter

        return MockAdapter(mode=config.mode)

    if config.adapter == "terminal":
        from .terminal import TerminalAdapter

        return TerminalAdapter(config)

    raise AdapterError(f"unknown adapter {config.adapter!r}")
