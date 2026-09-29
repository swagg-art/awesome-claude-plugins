# primexbt-signals

A Claude Code plugin that scans instruments available on PrimeXBT (crypto, gold,
FX, oil, indices) and produces **rule-based, explainable** trading signals:
long / short / neutral bias, a -6..+6 score, and ATR-based entry, stop and
take-profit levels.

It is analysis-only: no exchange keys, no order placement.

## Install

```bash
/plugin install ./plugins/primexbt-signals
```

## Use

```
/signals                     # default watchlist
/signals BTCUSD XAUUSD       # custom list
```

Or just ask: *"give me PrimeXBT signals for BTC and gold"*.

## How it works

1. Pulls daily candles from a connected market-data MCP (Crypto.com, Alpha Vantage).
2. Runs `skills/primexbt-signals/scripts/signals.py` (standard-library Python):
   EMA 10/30, MACD 12/26/9, RSI 14, 20-bar Donchian breakout, ATR 14.
3. Reports a table plus the reasons behind every vote.

See [`skills/primexbt-signals/SKILL.md`](skills/primexbt-signals/SKILL.md) for the exact rules.

## Example

[`examples/2026-09-29/`](examples/2026-09-29/) has a real snapshot (Crypto.com
daily candles, 11 Aug – 29 Sep 2026) and its output:

| Symbol | Close | Bias | Score | RSI | Entry | Stop | TP1 | TP2 |
|---|---|---|---|---|---|---|---|---|
| BTCUSD | 84,090 | NEUTRAL | +1 | 63.5 | - | - | - | - |
| ETHUSD | 2,713 | NEUTRAL | +1 | 65.9 | - | - | - | - |
| SOLUSD | 119.56 | LONG | +3 | 64.3 | 119.56 | 111.73 | 127.39 | 135.22 |
| XAUUSD* | 4,158 | SHORT | -5 | 31.9 | 4,158 | 4,252 | 4,064 | 3,969 |
| XRPUSD | 1.5060 | NEUTRAL | +1 | 58.3 | - | - | - | - |

\* Gold via PAXG/USD (gold-backed token) because the Alpha Vantage feed timed out.

## Tests

```bash
python3 -m unittest discover -s plugins/primexbt-signals/tests
```

## Disclaimer

Educational analysis only, not financial advice. Leveraged trading can lose more
than your deposit. Signals are mechanical and ignore news, funding and liquidity.
