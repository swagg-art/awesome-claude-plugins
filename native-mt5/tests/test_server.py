"""Smoke tests for the MCP wiring.

Skipped when the mcp package is absent, so the core suite still runs on a bare
checkout. When it is present these catch the mistakes the unit tests cannot:
a tool that fails to register, a decorator that eats the type hints, an
exception that escapes as a traceback instead of a readable payload.
"""

import asyncio
import json
import unittest

from native_mt5.config import Config
from native_mt5.safety import TradeMode
from native_mt5.session import Session

try:
    from native_mt5.server import build_server

    build_server(Session(Config()))
except (SystemExit, ImportError):  # pragma: no cover — depends on install extras
    MCP_AVAILABLE = False
else:
    MCP_AVAILABLE = True

EXPECTED_TOOLS = {
    "mt5_status",
    "mt5_account",
    "mt5_list_symbols",
    "mt5_symbol_info",
    "mt5_quote",
    "mt5_candles",
    "mt5_positions",
    "mt5_history",
    "mt5_performance",
    "mt5_size_position",
    "mt5_preview_order",
    "mt5_place_order",
    "mt5_close_position",
}


def payload(result):
    """Pull the JSON body out of a tool result, across SDK versions."""
    structured = getattr(result, "structured_content", None)
    if structured:
        return structured
    content = getattr(result, "content", None) or result[0]
    text = content[0].text if isinstance(content, list) else content
    return json.loads(text)


@unittest.skipUnless(MCP_AVAILABLE, "the mcp package is not installed")
class ServerTests(unittest.TestCase):
    def build(self, mode=TradeMode.READONLY):
        return build_server(Session(Config(adapter="mock", mode=mode)))

    def call(self, server, name, args):
        return payload(asyncio.run(server.call_tool(name, args)))

    def test_every_tool_is_registered(self):
        tools = asyncio.run(self.build().list_tools())
        self.assertEqual({t.name for t in tools}, EXPECTED_TOOLS)

    def test_tool_arguments_survive_the_error_wrapper(self):
        """The guard decorator must not flatten signatures into (*args, **kwargs)."""
        tools = {t.name: t for t in asyncio.run(self.build().list_tools())}
        schema = tools["mt5_size_position"].input_schema
        self.assertIn("stop_loss", schema["properties"])
        self.assertIn("symbol", schema["required"])

    def test_read_tools_answer(self):
        server = self.build()
        self.assertEqual(self.call(server, "mt5_status", {})["mode"], "readonly")
        self.assertGreater(self.call(server, "mt5_account", {})["balance"], 0)
        candles = self.call(server, "mt5_candles", {"symbol": "EURUSD", "count": 5})
        self.assertEqual(len(candles["candles"]), 5)

    def test_expected_failures_come_back_as_readable_payloads(self):
        server = self.build()
        order = {"symbol": "EURUSD", "side": "buy", "volume": 0.1}
        refused = self.call(server, "mt5_place_order", order)
        self.assertEqual(refused["error_type"], "SafetyError")
        self.assertIn("readonly", refused["error"])

        unknown = self.call(server, "mt5_quote", {"symbol": "NOPE"})
        self.assertEqual(unknown["error_type"], "AdapterError")

    def test_paper_mode_can_open_and_close_through_the_tools(self):
        server = self.build(TradeMode.PAPER)
        order = {"symbol": "EURUSD", "side": "buy", "volume": 0.1}
        opened = self.call(server, "mt5_place_order", order)
        self.assertTrue(opened["ok"])
        closed = self.call(server, "mt5_close_position", {"ticket": opened["ticket"]})
        self.assertTrue(closed["ok"])


if __name__ == "__main__":
    unittest.main()
