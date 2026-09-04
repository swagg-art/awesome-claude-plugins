# Native MT5

Native MetaTrader 5 access for AI agents, over MCP.

Thirteen tools that let a model read a real trading account — quotes, OHLC
history, contract specs, open positions, closed deals, performance — size a
position against a stop, and place orders behind guards that have to be
deliberately unlocked.

The default configuration is read-only against synthetic data. Getting to a
live order takes two explicit steps, and neither happens by accident.

## Why this exists

The MetaTrader 5 Python API is real but awkward: Windows-only wheels, integer
retcodes, tick values you have to reason about before you can size anything,
and no notion of "don't let this thing trade." Handing it to a model directly
means the model either can't do anything useful or can do far too much.

Native MT5 sits in between. It normalises the API into plain JSON, does the
position-sizing arithmetic that people get wrong, and puts a safety layer in
front of every write.

## Install

```bash
pip install -e '.[server]'          # the MCP server
pip install -e '.[server,terminal]' # plus the MetaTrader5 package (Windows)
```

Python 3.11+. The `MetaTrader5` package only publishes Windows wheels — on
macOS or Linux, run the terminal under Wine or point Native MT5 at a Windows
host. Everything except the `terminal` adapter works anywhere.

## Run it

```bash
native-mt5              # or: python -m native_mt5
```

With no environment set it comes up on the mock adapter in read-only mode,
which is the right way to see what the tools return before trusting them with
an account.

### As a Claude Code plugin

The `plugin/` directory is a ready-made Claude Code plugin: it registers the
MCP server, a `/mt5-review` command for a read-only account review, and an
`mt5-trade-plan` skill that teaches the model the order of operations.

## Configuration

Every setting is an environment variable with a safe default. See
[`.env.example`](.env.example) for the annotated list.

| Variable | Default | Meaning |
| --- | --- | --- |
| `NATIVE_MT5_ADAPTER` | `mock` | `mock` (synthetic) or `terminal` (real MT5) |
| `NATIVE_MT5_MODE` | `readonly` | `readonly`, `paper` or `live` |
| `NATIVE_MT5_LOGIN` / `PASSWORD` / `SERVER` | — | terminal credentials; blank attaches to an already logged-in terminal |
| `NATIVE_MT5_MAX_RISK_PER_TRADE_PCT` | `1.0` | ceiling the sizing tool clamps to |
| `NATIVE_MT5_MAX_ORDER_VOLUME` | `1.0` | hard lot cap per order |
| `NATIVE_MT5_MAX_OPEN_POSITIONS` | `10` | refuse new orders past this many |
| `NATIVE_MT5_SYMBOL_ALLOWLIST` | all | comma-separated whitelist |

## The safety model

Three modes, and reading is always allowed:

- **`readonly`** — market data and account inspection. Orders are refused.
  This is the default.
- **`paper`** — orders are simulated inside the adapter. Nothing reaches a
  broker.
- **`live`** — orders reach the broker, and each one needs a confirmation
  token.

The token comes from `mt5_preview_order` and is derived from the order itself,
so it is worthless for a different one: preview 0.1 lots, and the token will not
execute 1.0 lots. The intended flow is preview → show the human → they approve →
execute with the token. A model cannot manufacture one without first producing
a preview a person could read.

On top of that, every order — in any mode — is checked against the volume cap,
the open-position cap, the symbol allowlist, and stop/target sanity (a buy whose
stop sits above its target is refused).

## Tools

| Tool | What it does |
| --- | --- |
| `mt5_status` | Which account, which mode, what the caps are |
| `mt5_account` | Balance, equity, margin, floating profit |
| `mt5_list_symbols` | Search tradable instruments |
| `mt5_symbol_info` | Contract spec: digits, tick size/value, lot limits |
| `mt5_quote` | Bid, ask, spread |
| `mt5_candles` | OHLC history, M1 through MN1 |
| `mt5_positions` | Open positions with live floating P/L |
| `mt5_history` | Closed deals over N days |
| `mt5_performance` | Win rate, profit factor, net profit |
| `mt5_size_position` | Lot size for a given stop and risk % |
| `mt5_preview_order` | Dry run: cost, risk, and the confirmation token |
| `mt5_place_order` | Open a position (guarded) |
| `mt5_close_position` | Close by ticket (guarded) |

## Development

```bash
python -m unittest discover -s tests   # 61 tests, no dependencies needed
pytest                                 # same suite, if you prefer
```

The suite runs on a bare checkout: the core logic has no third-party imports,
and the MCP smoke tests skip themselves when the `mcp` package is absent.

Layout:

```
src/native_mt5/
  config.py         environment → validated Config
  safety.py         TradeMode, Guard, confirmation tokens
  risk.py           position sizing and performance stats (pure math)
  session.py        the tool layer — all behaviour lives here
  server.py         thin MCP wrapper over Session
  adapters/
    base.py         the interface every backend implements
    mock.py         deterministic synthetic broker
    terminal.py     the real MetaTrader5 package
```

`Session` is deliberately independent of MCP, so the same behaviour can be
driven from tests, a CLI, or a future HTTP front end without duplication.

## Status and limits

Alpha. Known gaps, in rough order of how much they matter:

- Market orders only — no pending orders, no partial closes, no stop/target
  modification on an open position.
- No backtesting. `mt5_candles` gives a model the data to reason over, but
  there is no engine behind it.
- The mock adapter's random walk is for exercising the plumbing. It is not a
  market simulator and must not be used to evaluate a strategy.
- Single account per server process.

## Licence

MIT.
