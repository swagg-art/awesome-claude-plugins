# Native MT5 — build summary

**Date:** 2026-09-04
**Branch:** `claude/native-mt5-project-name-webv15`
**Location:** `native-mt5/` (new sub-project; the existing `ui/` directory site is untouched)

## What was built

An MCP server that gives an AI agent native access to a MetaTrader 5 account —
market data, account state, position sizing, and order execution behind safety
guards — plus a Claude Code plugin wrapper around it.

### The tool surface — 13 tools

| Tool | Access |
| --- | --- |
| `mt5_status`, `mt5_account` | read |
| `mt5_list_symbols`, `mt5_symbol_info`, `mt5_quote`, `mt5_candles` | read |
| `mt5_positions`, `mt5_history`, `mt5_performance` | read |
| `mt5_size_position`, `mt5_preview_order` | read (computes, never executes) |
| `mt5_place_order`, `mt5_close_position` | **write — guarded** |

### The safety model

This was the main design constraint: a model with a broker connection can lose
real money, so writes had to be hard to reach by accident.

- **Three modes.** `readonly` (default) refuses all orders; `paper` simulates
  them inside the adapter; `live` reaches the broker.
- **Confirmation tokens.** In live mode every order needs a token from
  `mt5_preview_order`, derived by hash from the order's own parameters. A token
  for 0.1 lots will not execute 1.0 lots. A model cannot mint one without first
  producing a preview a human can read.
- **Caps, checked before the adapter sees anything.** Max lot size, max open
  positions, symbol allowlist, and a risk-percentage ceiling the sizing tool
  clamps to.
- **Stop sanity.** A buy whose stop sits above its target is refused outright.
- **`live` + `mock` is rejected at config time** as a meaningless combination.

### Architecture

```
src/native_mt5/
  config.py       environment → validated Config (password never in describe())
  safety.py       TradeMode, Guard, confirmation tokens
  risk.py         position sizing + performance stats — pure math, no imports
  session.py      the tool layer; all behaviour lives here
  server.py       thin MCP wrapper over Session
  adapters/
    base.py       the interface every backend implements
    mock.py       deterministic synthetic broker (seeded random walk)
    terminal.py   the real MetaTrader5 package
```

Two decisions worth recording:

1. **`Session` is independent of MCP.** Every tool is a one-line wrapper over a
   `Session` method, so the entire surface is testable without the MCP runtime
   and a future CLI or HTTP front end gets identical behaviour for free.
2. **The mock adapter is a first-class backend, not a test fixture.** The
   `MetaTrader5` package only ships Windows wheels. Without a mock, the project
   would be undevelopable and untestable on Linux and macOS, and unusable for
   anyone evaluating it before wiring a broker.

## Verification

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests` (bare, no deps) | **61 tests OK** (5 MCP tests self-skip) |
| `pytest -q` with `mcp` installed | **61 passed** |
| `ruff check src tests` | **All checks passed** |
| MCP tool registration | all 13 tools registered with correct JSON schemas |
| End-to-end tool calls | status / quote / sizing / refused order all verified live |

Beyond unit coverage, the following were confirmed by actually running the
server against the installed SDK:

- The error-wrapping decorator preserves type hints — an early version used
  `*args, **kwargs` and silently flattened every tool schema to no parameters.
  There is now a regression test for this.
- Expected failures surface as `{"error": ..., "error_type": ...}` payloads a
  model can read, not tracebacks.
- A `readonly` server refuses `mt5_place_order` with an actionable message.

## Compatibility notes

- **MCP SDK 1.x and 2.x both work.** The SDK renamed `FastMCP` to `MCPServer` in
  2.0 without changing the decorator API; `_load_server_class()` tries both, so
  users are not pinned to one major version.
- **Python 3.11+.** CI runs 3.11 and 3.12.
- **The `terminal` adapter needs Windows** (or the terminal under Wine). Every
  other part of the project runs anywhere.

## CI

`.github/workflows/native-mt5.yml`, path-scoped to `native-mt5/**` so it never
runs on changes to the existing `ui/` site, and the existing `ui` CI is
unaffected. It runs the suite twice — once with no dependencies installed, to
prove the bare-checkout path stays working, then again with the server extra —
plus ruff.

## Known gaps

In rough order of how much they matter:

- Market orders only. No pending orders, no partial closes, no modifying stops
  on an open position.
- No backtesting engine. `mt5_candles` gives a model data to reason over, but
  nothing evaluates a strategy.
- The mock adapter's random walk exercises the plumbing. It is **not** a market
  simulator and must not be used to judge a strategy.
- One account per server process.
- The terminal adapter's paths are unit-tested only through the shared
  interface; they need a real terminal for an integration test.
