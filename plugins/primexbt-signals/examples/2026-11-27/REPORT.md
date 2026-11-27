# PrimeXBT signals: summary report, 27 Nov 2026

Dashboard: https://claude.ai/artifact/EBSo1BWDySDvNNAytLXA3s

## Signals (daily, 50 bars)

| Symbol | Bias | Score | Close | RSI | 30d % | Stop | TP1 | TP2 |
|---|---|---|---|---|---|---|---|---|
| EURUSD | SHORT | -3 | 1.0967 | 34.8 | -2.2 | 1.1067 | 1.0867 | 1.0767 |
| XAUUSD | SHORT | -3 | 3,568 | 30.7 | -12.2 | 3,634 | 3,501 | 3,435 |
| SOLUSD | NEUTRAL | -1 | 72.01 | 35.1 | -29.6 | - | - | - |
| XRPUSD | NEUTRAL | -1 | 0.9512 | 35.3 | -28.2 | - | - | - |
| BTCUSD | NEUTRAL | 0 | 59,908 | 26.8 | -26.3 | - | - | - |
| ETHUSD | NEUTRAL | 0 | 1,672 | 28.5 | -29.1 | - | - | - |

## Market read

- No long signals. The four coins fell 26–30% over 30 days. Their trend votes point down, but MACD has
  turned up, so the votes cancel out to neutral.
- BTC and ETH have RSI below 30 (oversold). A long needs EMA10 to cross back above EMA30.
- Gold and EUR/USD score -3 (SHORT). Shorts lost money in every backtest, so treat these as the weakest
  kind of call.

## Scorecard: the 29 Sep 13:00 UTC calls

| Call | Outcome |
|---|---|
| ETH LONG, stop 2,593 | Stopped out 7 Oct, -1R |
| SOL LONG, stop 112.89 | Stopped out 8 Oct, -1R |
| XRP LONG, stop 1.412 | Stopped out 7 Oct, -1R |
| Gold SHORT, TP2 3,970 | TP2 hit 30 Oct (spot XAU close), +2R |

Net about -1R before costs. Four trades is far too few to judge the rules, but this result went against
the backtest, where longs did best and shorts lost.

## Data

- Crypto: Alpha Vantage `DIGITAL_CURRENCY_DAILY` to 26 Nov, plus Crypto.com's 27 Nov bar, still open
  at about 19:00 UTC. Crypto.com returned only 12–15 daily bars today, short of the 35 needed.
- Gold: Alpha Vantage `GOLD_SILVER_HISTORY` daily spot XAU. It is close-only, so o=h=l=c and the ATR,
  stop and targets are approximate.
- EUR/USD: Alpha Vantage `FX_DAILY`, to the 26 Nov close.

Reproduce: `python3 ../../skills/primexbt-signals/scripts/signals.py *.csv`

_Educational analysis only, not financial advice. No orders were placed._
