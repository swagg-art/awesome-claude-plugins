# trading — MetaTrader 5 skill

Trade and analyse an MT5 account from the command line. Orders go out when you
ask for them; what happens first is validation, not a confirmation prompt.

```
mt5ctl ──▶ MetaTrader5 (Python API) ──▶ MT5 terminal ──▶ broker
```

## Install

```bash
# macOS
mkdir -p ~/Library/Application\ Support/Claude/skills
cp -r claude-skill/trading ~/Library/Application\ Support/Claude/skills/trading

# Windows
mkdir "%APPDATA%\Claude\skills"
xcopy /E /I claude-skill\trading "%APPDATA%\Claude\skills\trading\"
```

Those paths are **Claude Desktop's**. For **Claude Code**, personal skills live
in `~/.claude/skills/` instead:

```bash
mkdir -p ~/.claude/skills
cp -r claude-skill/trading ~/.claude/skills/trading
```

Then, on the machine running the MT5 terminal:

```bash
pip install MetaTrader5
ln -s "$PWD/claude-skill/trading/scripts/mt5ctl" ~/.local/bin/mt5ctl
mt5ctl account
```

**The `MetaTrader5` package is Windows-only.** On macOS or Linux you need a
Windows VM, Wine, or a bridge to a Windows host — see `reference/setup.md`. The
sizing, journal and backtest maths run anywhere.

## What's here

| Path | What it is |
|---|---|
| `SKILL.md` | The execution contract, commands, workflows |
| `scripts/mt5ctl` | The CLI — 17 subcommands, terminal tables, `--json` |
| `scripts/mt5_client.py` | Validated wrapper over the MetaTrader5 API |
| `scripts/risk.py` | Position sizing, R multiples, portfolio heat |
| `scripts/journal.py` | Deal history → round-trip trades → statistics |
| `scripts/backtest.py` | Bar-based engine, three strategies, SMA/RSI/ATR |
| `scripts/tables.py` | Box-drawn table rendering |
| `reference/` | MT5 domain, workflows, setup, analysis |
| `tests/` | 78 tests against a stub terminal |

## Commands

```bash
mt5ctl account                    # balance, equity, margin, DEMO or LIVE
mt5ctl positions [SYMBOL]         # open positions with floating P&L
mt5ctl orders                     # working pending orders
mt5ctl quote EURUSD XAUUSD        # bid/ask/spread, lot constraints
mt5ctl symbols GOLD               # what this broker calls it
mt5ctl bars EURUSD --tf H1

mt5ctl buy  EURUSD 0.10 --sl 1.0820 --tp 1.0900
mt5ctl sell XAUUSD 0.05 --sl 2325.00
mt5ctl pending EURUSD buy limit 0.10 1.0800
mt5ctl modify 880011 --sl 1.0850
mt5ctl close 880011 [--volume 0.05]
mt5ctl close-all [--symbol EURUSD]
mt5ctl cancel 880042

mt5ctl size EURUSD --risk 1 --entry 1.0850 --stop 1.0820
mt5ctl heat

mt5ctl journal sync --days 90
mt5ctl journal stats --by-symbol
mt5ctl backtest EURUSD --tf H1 --strategy ma_cross --param fast=8 --spread 12
```

`--dry-run` prints the request without sending. `--json` gives machine-readable
output on any command.

## Bounds

`~/.config/mt5-trading/config.json` sets `max_volume`, `allowed_symbols`,
`default_deviation`, `magic` and `dry_run`. A fat-fingered size fails locally
rather than at the broker. Start from `config/config.example.json`, `chmod 600`
it, and never commit it.

## Validation before the broker sees it

- Symbol resolved against the broker's real names (`EURUSD` → `EURUSD.raw`),
  ambiguity reported rather than guessed
- Volume rounded to `volume_step`, checked against min/max and your cap
- Filling mode chosen from the symbol's `filling_mode` bitmask (avoids 10030)
- Stops checked for side and for the broker's minimum distance (avoids 10016)
- Pending orders checked against the market (a buy limit above the market is
  refused)
- Requotes retried twice with a refreshed price; every other retcode raises
  with a plain-English reason

## Tests

```bash
python3 -m unittest discover -s tests -v
```

78 tests, stdlib only, no terminal or network — a stub stands in for the
MetaTrader5 package and records what would have been sent.

## Scope

This executes and measures what you decide to trade. It does not recommend
trades, and nothing in it is financial advice. Trading leveraged instruments
can lose more than the deposit.
