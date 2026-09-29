# PrimeXBT signals: summary report, 29 Sep 2026

Dashboard: https://claude.ai/artifact/EBSo1BWDySDvNNAytLXA3s

## Signals (daily, Crypto.com data, 50 bars, today's bar still open)

| Symbol | Bias | Score | Close | RSI | Stop | TP1 | TP2 |
|---|---|---|---|---|---|---|---|
| SOLUSD | LONG | +3 | 119.56 | 64.3 | 111.73 | 127.39 | 135.22 |
| XAUUSD (PAXG) | SHORT | -5 | 4,158 | 31.9 | 4,252 | 4,064 | 3,969 |
| BTCUSD | NEUTRAL | +1 | 84,090 | 63.5 | - | - | - |
| ETHUSD | NEUTRAL | +1 | 2,713 | 65.9 | - | - | - |
| XRPUSD | NEUTRAL | +1 | 1.5060 | 58.3 | - | - | - |

## Market read

- Crypto is in a recovery uptrend (BTC +8.3% over 30 days); every coin is above its EMA30.
- Momentum is cooling: MACD histograms are negative on BTC, ETH and XRP, keeping them neutral.
- SOL is the only long; MACD is still positive and RSI is bullish without being overbought.
- Gold is the strongest call (short, -5) after a month-long slide (-6.6%). RSI near 32 means a bounce is plausible.

## What was built

- `plugins/primexbt-signals`: plugin manifest, `primexbt-signals` skill, `/signals` command.
- `scripts/signals.py`: standard-library engine (EMA, MACD, RSI, Donchian, ATR); markdown or JSON output.
- `tests/test_signals.py`: 5 unit tests, all passing.
- This folder: input candles, `signals.md`, `signals.json`, this report.

## Gaps

- EUR/USD and WTI were dropped: Alpha Vantage timed out on two attempts.
- Gold uses PAXG/USD as a proxy for XAU/USD.
- No backtest; rules ignore news, funding and liquidity.

_Educational analysis only, not financial advice. No orders were placed._
