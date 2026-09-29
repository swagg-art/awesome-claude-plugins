---
name: primexbt-signals
description: Generate rule-based technical trading signals for PrimeXBT instruments (BTC, ETH, SOL, XRP, gold, FX majors, oil, indices). Use when the user asks for PrimeXBT signals, trade ideas, a market scan, long/short bias, entry/stop/take-profit levels, or a signals report for crypto, gold or forex.
---

# PrimeXBT Signals

Produce a transparent, reproducible signal for each instrument from daily OHLC
candles. The skill never places trades; it outputs analysis only.

## 1. Pick the watchlist

Default: `BTCUSD ETHUSD SOLUSD XRPUSD XAUUSD EURUSD`. Use the user's list if given.

## 2. Fetch at least 35 daily candles per symbol

Use whichever market-data source is connected, in this order:

| Asset class | Preferred source | Call |
|---|---|---|
| Crypto | Crypto.com MCP | `get_candlestick(instrument_name="BTC_USD", timeframe="1D")` |
| Gold | Alpha Vantage `GOLD_SILVER_HISTORY(symbol="XAU", interval="daily")`; fallback Crypto.com `PAXG_USD` (gold-backed token, tracks spot closely) |
| FX | Alpha Vantage `FX_DAILY(from_symbol="EUR", to_symbol="USD")` |
| Oil | Alpha Vantage `WTI(interval="daily")` (close-only: set o=h=l=c) |
| Indices | Alpha Vantage `TIME_SERIES_DAILY` on an ETF proxy (SPY, QQQ) |

If a source fails, retry once, then drop that symbol and say so in the report.

Save each series to `<dir>/<SYMBOL>.csv` with header `t,o,h,l,c`
(or save the raw Crypto.com JSON — the script reads it directly).

## 3. Run the engine

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/primexbt-signals/scripts/signals.py <dir>/*.csv          # markdown
python3 ${CLAUDE_PLUGIN_ROOT}/skills/primexbt-signals/scripts/signals.py <dir>/*.csv --json   # data
```

Scoring (each rule votes +1 / -1 / 0, range -6..+6):

1. EMA10 vs EMA30 (trend)
2. Close vs EMA30 (trend location)
3. MACD(12,26,9) histogram sign (momentum)
4. MACD histogram rising/falling (momentum change)
5. RSI(14) in 55–70 (+1) or 30–45 (-1)
6. Close beyond prior 20-bar high (+1) / low (-1)

`score >= +3` → LONG, `<= -3` → SHORT, otherwise NEUTRAL.
Levels use ATR(14): stop 1.5×ATR, TP1 1.5×ATR (1R), TP2 3×ATR (2R).
RSI ≥ 70 / ≤ 30 adds a "don't chase" warning.

## 4. Report

Show the table, one line of reasoning per symbol, and the warnings. Then:

- Suggest position size from risk, not leverage: `size = (equity × risk%) / |entry − stop|`
  (default risk 1%). Note PrimeXBT's high leverage magnifies losses.
- State the data timestamp and source for every symbol.
- Always end with: *Educational analysis only, not financial advice.*
- Never execute or suggest executing an order without the user's explicit request.
