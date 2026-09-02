# Setup

## The platform constraint, first

The official `MetaTrader5` Python package is **Windows-only**. It talks to a
running MT5 terminal through a local IPC channel that exists only on Windows.
There is no macOS or Linux build.

So on macOS or Linux you have three options:

1. **Run everything on Windows** — a PC, a VM (Parallels, UTM, VirtualBox), or
   a Windows VPS near the broker. Simplest and what most people do.
2. **Wine.** MT5 itself runs under Wine, and so does a Windows Python inside the
   same prefix. Workable, fiddly to keep alive across updates.
3. **A bridge.** Run `mt5ctl` on your machine and a small socket server on the
   Windows box beside the terminal. Nothing here ships one, but the client's
   surface is small enough to proxy if you want to build one.

Everything except the live terminal calls — `size`, the journal maths, the
backtester on exported bars — is pure Python and runs anywhere.

## Install

On the machine with the terminal:

```bash
pip install MetaTrader5
```

Then put `mt5ctl` on PATH:

```bash
# macOS / Linux
ln -s /path/to/claude-skill/trading/scripts/mt5ctl ~/.local/bin/mt5ctl

# Windows (PowerShell, from the scripts directory)
$env:Path += ";$PWD"
```

Or call it directly: `python3 /path/to/scripts/mt5ctl account`.

## Terminal configuration

Three things must be true or every order fails:

1. **The terminal is running and logged in.** The Python API attaches to a
   running terminal; it does not start a headless one for you.
2. **Algo Trading is enabled.** The toolbar button, or Tools → Options →
   Expert Advisors → "Allow algorithmic trading". Without it, orders come back
   with retcode **10027**.
3. **The symbol is in Market Watch.** `mt5ctl` selects symbols automatically,
   but a symbol your broker does not offer on your account type simply is not
   there.

Check all three at once:

```bash
mt5ctl account
```

If that prints a table with your login and balance, the connection is good.

## Credentials

`mt5ctl` attaches to whatever account the terminal is already logged into, so
credentials are optional. Supply them only if you want it to log in itself:

```json
{
  "login": 12345678,
  "password": "…",
  "server": "BrokerX-Demo",
  "terminal_path": "C:\\Program Files\\MetaTrader 5\\terminal64.exe"
}
```

Saved at `~/.config/mt5-trading/config.json` (override with `MT5_CONFIG`).
Environment variables `MT5_LOGIN`, `MT5_PASSWORD` and `MT5_SERVER` take
precedence, which is the better option on a shared box.

```bash
chmod 600 ~/.config/mt5-trading/config.json
```

Never commit this file. A copy of `config/config.example.json` is the starting
point.

## Bounds worth setting

```json
{
  "max_volume": 0.50,
  "max_open_positions": 20,
  "allowed_symbols": ["EURUSD", "GBPUSD", "XAUUSD"],
  "default_deviation": 20,
  "magic": 777001,
  "dry_run": false
}
```

- `max_volume` — a hard ceiling per order. A fat-fingered 10 lots fails here
  rather than at the broker.
- `allowed_symbols` — prefix matched, so `EURUSD` also permits `EURUSD.raw`.
  Empty means everything.
- `default_deviation` — maximum slippage in points on market orders.
- `dry_run` — makes every order print instead of send. Useful while you are
  getting a new broker's symbol names right.

## Start on demo

Run against a demo account until the symbol names, lot steps and filling modes
are confirmed for your broker. `mt5ctl account` prints **DEMO** or **LIVE** on
every call, so there is no ambiguity about which one you are on.

## Verifying without a terminal

The test suite runs anywhere — it drives a stub in place of the MetaTrader5
package:

```bash
python3 -m unittest discover -s tests -v
```
