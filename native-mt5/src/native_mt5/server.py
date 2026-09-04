"""MCP server exposing the Native MT5 tool surface.

Thin by design: each tool validates nothing on its own and delegates to
`Session`, which is where the behaviour and the tests live. Errors are turned
into readable strings rather than tracebacks, because the model reads them.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from .adapters.base import AdapterError
from .config import Config, ConfigError
from .risk import RiskError
from .safety import SafetyError
from .session import Session

_HANDLED = (AdapterError, ConfigError, RiskError, SafetyError, ValueError)


def _guarded(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Turn expected failures into an `{"error": ...}` payload."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except _HANDLED as exc:
            return {"error": str(exc), "error_type": type(exc).__name__}

    return wrapper


def _load_server_class():
    """Find the MCP server class across SDK versions.

    The Python SDK renamed FastMCP to MCPServer in 2.0 without changing the
    decorator API we rely on, so both names work here and users are not forced
    onto one major version.
    """

    try:
        from mcp.server.mcpserver import MCPServer

        return MCPServer
    except ImportError:
        pass

    try:
        from mcp.server.fastmcp import FastMCP

        return FastMCP
    except ImportError as exc:  # pragma: no cover — depends on install extras
        raise SystemExit(
            "the 'mcp' package is required to run the server. "
            "Install it with: pip install 'native-mt5[server]'"
        ) from exc


def build_server(session: Session | None = None):
    """Construct the FastMCP server with every tool registered."""

    server_class = _load_server_class()
    session = (session or Session()).open()
    mcp = server_class("native-mt5")

    @mcp.tool()
    @_guarded
    def mt5_status() -> dict:
        """Report which account this server is attached to and what it may do.

        Call this first in any session: it tells you whether trading is enabled
        (readonly / paper / live) and what the risk caps are.
        """
        return session.status()

    @mcp.tool()
    @_guarded
    def mt5_account() -> dict:
        """Balance, equity, margin, free margin and floating profit."""
        return session.account()

    @mcp.tool()
    @_guarded
    def mt5_list_symbols(search: str = "", limit: int = 50) -> dict:
        """List tradable instruments, optionally filtered by a substring.

        Brokers rename instruments (EURUSD.m, XAUUSD_i, …), so search rather
        than assuming a name.
        """
        return session.list_symbols(search, limit)

    @mcp.tool()
    @_guarded
    def mt5_symbol_info(symbol: str) -> dict:
        """Contract specification: digits, point, tick size/value, lot limits."""
        return session.symbol_info(symbol)

    @mcp.tool()
    @_guarded
    def mt5_quote(symbol: str) -> dict:
        """Current bid, ask and spread for one symbol."""
        return session.quote(symbol)

    @mcp.tool()
    @_guarded
    def mt5_candles(symbol: str, timeframe: str = "H1", count: int = 100) -> dict:
        """OHLC history. Timeframes: M1 M5 M15 M30 H1 H4 D1 W1 MN1."""
        return session.candles(symbol, timeframe, count)

    @mcp.tool()
    @_guarded
    def mt5_positions(symbol: str = "") -> dict:
        """Open positions with live floating profit, optionally for one symbol."""
        return session.positions(symbol)

    @mcp.tool()
    @_guarded
    def mt5_history(days: int = 30) -> dict:
        """Closed deals over the last N days."""
        return session.history(days)

    @mcp.tool()
    @_guarded
    def mt5_performance(days: int = 30) -> dict:
        """Win rate, profit factor and net profit over the last N days."""
        return session.performance(days)

    @mcp.tool()
    @_guarded
    def mt5_size_position(
        symbol: str,
        side: str,
        entry: float,
        stop_loss: float,
        risk_pct: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """Lot size that risks `risk_pct` of balance if the stop is hit.

        Rounds down to the broker's volume step and clamps to the server's risk
        ceiling. Use this instead of guessing a volume.
        """
        return session.size_position(symbol, side, entry, stop_loss, risk_pct, take_profit)

    @mcp.tool()
    @_guarded
    def mt5_preview_order(
        symbol: str,
        side: str,
        volume: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """Dry-run an order: cost, risk, and whether the guards would accept it.

        Never reaches the broker. In live mode this also returns the
        confirmation token that place_order requires — show the preview to the
        human before using it.
        """
        return session.preview_order(symbol, side, volume, stop_loss, take_profit)

    @mcp.tool()
    @_guarded
    def mt5_place_order(
        symbol: str,
        side: str,
        volume: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        comment: str = "",
        confirm_token: str | None = None,
    ) -> dict:
        """Open a market position. Refused outright in readonly mode.

        In live mode `confirm_token` must be the token from mt5_preview_order
        for exactly these arguments.
        """
        return session.place_order(
            symbol, side, volume, stop_loss, take_profit, comment, confirm_token
        )

    @mcp.tool()
    @_guarded
    def mt5_close_position(ticket: int) -> dict:
        """Close one open position by ticket. Refused in readonly mode."""
        return session.close_position(ticket)

    return mcp


def main() -> None:
    """Entry point for `native-mt5` / `python -m native_mt5`."""
    try:
        config = Config.from_env()
    except ConfigError as exc:
        raise SystemExit(f"native-mt5: bad configuration — {exc}") from exc
    build_server(Session(config)).run()


if __name__ == "__main__":  # pragma: no cover
    main()
