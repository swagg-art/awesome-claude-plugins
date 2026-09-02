# Project summary — MT5 trading skill

**Repository:** swagg-art/awesome-claude-plugins
**Branch:** `claude/computer-remote-7bgr8a` (committed `00b819c`; **push blocked** — see Status)
**Date:** 2026-09-02
**Location:** `claude-skill/trading/` — matching the install commands provided

## Scope as agreed

Requested: a trading skill with **direct execution** (trades placed immediately
when requested, no extra confirmation), **workflows** that chain tool calls
(market order then SL/TP), **terminal-style table formatting**, and **MT5 domain
knowledge** (order types, timeframes, symbol formats, filling modes) — layered
over market analysis, trade journalling, risk sizing and backtesting.

## What was built

| Component | File | Notes |
|---|---|---|
| MT5 client | `scripts/mt5_client.py` | ~510 lines. Validated wrapper over the MetaTrader5 API; constants mirrored so nothing imports the package to be tested. |
| CLI | `scripts/mt5ctl` | 17 subcommands, box-drawn tables, `--dry-run`, `--json`. |
| Risk | `scripts/risk.py` | Position sizing, R multiples, portfolio heat. Pure functions. |
| Journal | `scripts/journal.py` | Deal history → round-trip trades → statistics. JSONL store. |
| Backtester | `scripts/backtest.py` | Bar engine, SMA/RSI/ATR, three strategies. |
| Tables | `scripts/tables.py` | Alignment-checked terminal rendering. |
| Skill | `SKILL.md` | Execution contract, commands, workflows, presentation rules. |
| References | `reference/{mt5-domain,workflows,setup,analysis}.md` | Domain tables, recipes, install, metric definitions. |
| Tests | `tests/test_trading.py` + `tests/stub_mt5.py` | 78 tests against a stub terminal. |
| CI | `.github/workflows/ci.yml` | Added to the existing `plugins` job. |

## The execution contract

The user asked for no confirmation step, and that is how it is built: a trade
request is the authorization, and `mt5ctl buy EURUSD 0.10` sends. What the skill
still does — none of which is a confirmation prompt:

- **Never invents a missing parameter.** No volume given → ask for the volume.
- **Resolves genuine ambiguity.** "Close EURUSD" with a long and a short open
  → show both, ask which. "Close my EURUSD long" → close it.
- **Validates before the broker sees it**, and reports failures rather than
  retrying blindly.

## Validation layer

This is where the engineering value sits — each check maps to a specific MT5
rejection that would otherwise arrive as an opaque retcode:

| Check | Prevents |
|---|---|
| Symbol resolution across broker suffixes (`EURUSD` → `EURUSD.raw`), ambiguity reported | "unknown symbol" on a broker that renamed it |
| Volume rounded to `volume_step`, bounded by min/max and config `max_volume` | 10014 invalid volume |
| Filling mode chosen from the symbol's `filling_mode` bitmask | 10030 unsupported filling mode |
| Stop side and `trade_stops_level` minimum distance | 10016 invalid stops |
| Pending price checked against the market per order type | Rejected buy-limit-above-market |
| Close sends the opposite side carrying the `position` ticket | Opening a hedged second position instead of closing |
| Requote (10004/10020/10021) retried twice with a refreshed price | Spurious failures on fast markets |

Every other retcode raises with a plain-English reason from a 20-entry table.

## Bounds

`~/.config/mt5-trading/config.json` carries `max_volume`, `allowed_symbols`
(prefix-matched), `default_deviation`, `magic` and `dry_run`. A fat-fingered
size fails locally instead of at the broker. The skill treats these as the
user's own limits: when an order trips one it reports and stops rather than
widening the config.

## Verification

- **78 tests pass** (`python3 -m unittest discover -s tests`). Coverage:
  symbol resolution incl. ambiguity, volume rounding and all three rejection
  paths, filling-mode preference order, stop validation incl. broker stop
  level, market/pending request construction (buy lifts the ask, sell hits the
  bid), dry-run sending nothing, allowlist enforcement, requote retry vs hard
  rejection, partial close limits, SL/TP action shape, sizing maths and its
  three refusals, R multiples, portfolio heat with unprotected positions,
  journal folding incl. partial exits and costs, stats and drawdown, merge
  preserving local notes, indicator correctness, no-lookahead fills, intrabar
  stops, spread cost, and table alignment.
- **End-to-end CLI run** against a module-level fake `MetaTrader5`: account,
  positions, quote, dry-run buy, live buy, rejected stop, size, heat, journal
  sync → note → list → stats, and a 600-bar backtest all rendered correctly.
- **Two bugs found and fixed by that run**: prices were being flattened to 2dp
  in order tables (now full precision), and record conversion assumed every row
  exposes `_asdict()` (now tolerant, raising a clear error instead of
  `AttributeError`).
- Backtester sanity-checked on a random walk: MA-cross loses money on noise,
  which is the expected result and a signal the engine is not manufacturing
  edge.
- The computer-remote suite (25 tests) is still green; CI YAML parses.

## Known limits, stated in the docs

- **The `MetaTrader5` package is Windows-only.** macOS/Linux need a Windows VM,
  Wine, or a bridge. Sizing, journal and backtest maths run anywhere.
- Backtester models: next-bar-open fills, one position at a time, fixed spread,
  stop-before-target when both are hit intrabar. It does **not** model swap,
  commission, slippage, partial fills or margin calls, and reports points, not
  currency.
- No OCO — bracketing with two pending orders requires cancelling the unfilled
  side manually.
- Journal skips still-open positions rather than half-counting them.

## Status

The commit `00b819c` exists locally on `claude/computer-remote-7bgr8a`. The
`git push` was **denied by the permission classifier**, so the branch is not
yet on the remote and nothing has been published. The work is complete and
verified; it needs either a push permission or a manual push to land.

Note also that both projects in this session share one designated branch, so
this commit sits on top of the computer-remote plugin commit.

## Scope note

The skill executes and measures what the user decides to trade. It does not
recommend trades and contains no financial advice.
