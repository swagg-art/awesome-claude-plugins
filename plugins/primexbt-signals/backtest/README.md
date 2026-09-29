# Backtest: primexbt-signals rules

Walk-forward test of `signals.py` with `scripts/backtest.py`. At every bar the
engine sees only the previous 50 bars (the same history the live skill uses),
enters at the **next bar's open**, and exits at the ATR stop or target. When a
bar touches both, the stop is assumed first. Results are in **R** (multiples
of the 1.5×ATR initial risk) after costs.

Reproduce:

```bash
S=skills/primexbt-signals/scripts
python3 $S/backtest.py backtest/data/EURUSD_H1.csv --cost-pct 0.01
python3 $S/backtest.py backtest/data/GOOG_D1.csv backtest/data/BTCUSD_MN.csv --cost-pct 0.1
python3 $S/backtest.py backtest/data/*.csv --long-only          # variant
```

## Data

This session had no network route to exchange APIs, and the Alpha Vantage feed
timed out, so the test uses the real OHLC datasets bundled with the open-source
[`backtesting`](https://pypi.org/project/backtesting/) package (v0.6.6):

| File | Market | Bars | Period | Cost used (round trip) |
|---|---|---|---|---|
| `EURUSD_H1.csv` | EUR/USD, hourly | 5,000 | Apr 2017 – Feb 2018 | 0.01% (~1 pip) |
| `GOOG_D1.csv` | Alphabet stock, daily | 2,148 | Aug 2004 – Mar 2013 | 0.10% |
| `BTCUSD_MN.csv` | Bitcoin, monthly | 156 | Jan 2012 – Dec 2024 | 0.10% |

**The rules have not yet been tested on daily crypto or gold, which is what
the live signals trade.**

## Results (base rules: stop 1.5×ATR, target 3×ATR = 2R)

| Market | Trades | Win % | Expectancy | Profit factor | Max DD | Return @1% risk | 2× costs |
|---|---|---|---|---|---|---|---|
| EUR/USD H1 | 358 | 36.0 | +0.03R | 1.04 | −16.5R | +5.5% | −0.03R |
| GOOG D1 | 169 | 42.6 | +0.21R | 1.34 | −8.7R | +40.6% | +0.18R |
| BTC monthly | 24 | 58.3 | +0.78R | 3.03 | −3.0R | +20.2% | +0.78R |

## Variants

| Variant | EUR/USD H1 | GOOG D1 | BTC monthly |
|---|---|---|---|
| Base (stop / 2R target) | +0.03R, PF 1.04 | +0.21R, PF 1.34 | +0.78R, PF 3.03 |
| Long only | **+0.22R, PF 1.36** | **+0.45R, PF 1.87** | +0.86R, PF 3.41 |
| 1R target (TP1) | −0.01R, PF 0.97 | +0.13R, PF 1.30 | +0.18R, PF 1.44 |
| Exit when bias flips | −0.06R, PF 0.82 | +0.10R, PF 1.34 | +0.69R, PF 3.32 |

Expectancy is per trade. Split into halves, every GOOG and BTC variant was
positive in both. EUR/USD long-only was positive in both halves (+0.19R, +0.27R)
and exit-on-flip negative in both. The base and 1R-target EUR/USD runs changed
sign between halves, which is what noise around zero looks like.

## Findings

1. **Longs carry the edge; shorts lose money on all three markets.** Short
   trades summed −35.6R on EUR/USD, −10.3R on GOOG and −1.0R on BTC.
2. **The 2R target beats the 1R target.** Taking profit at 1R roughly halves
   expectancy or turns it negative.
3. **Don't exit when the score drops back to neutral.** That exit cut 76% of
   EUR/USD trades short and turned the result negative.
4. **On EUR/USD H1 the base rules are break-even**, and doubling costs makes
   them lose. The edge there is too thin to trade.
5. **Trend-following only did well in trending samples.** All three periods
   rose strongly. Buy and hold beat the rules on GOOG (+317%) and BTC, though
   the rules risked only 1% per trade.

## Every timeframe

The same rules and the same 50-bar lookback on every timeframe the data allows.
Higher timeframes are built by grouping the real bars (`--resample`), so
2h to 1d EUR/USD comes from the hourly file and weekly and monthly GOOG from
the daily file.

```bash
python3 skills/primexbt-signals/scripts/backtest.py backtest/data/EURUSD_H1.csv --cost-pct 0.01 --resample 4h
```

| Market | Timeframe | Bars | Trades | Base expectancy | Base PF | Long-only expectancy | Long-only PF | Short R total |
|---|---|---|---|---|---|---|---|---|
| EUR/USD | 1h | 5,000 | 358 | +0.03R | 1.04 | **+0.22R** | 1.36 | −35.6 |
| EUR/USD | 2h | 2,528 | 189 | +0.09R | 1.13 | **+0.24R** | 1.40 | −12.9 |
| EUR/USD | 4h | 1,292 | 96 | +0.01R | 1.01 | **+0.23R** | 1.39 | −15.9 |
| EUR/USD | 8h | 667 | 58 | −0.14R | 0.80 | +0.12R | 1.19 | −12.3 |
| EUR/USD | 1d | 251 | 16 | +0.32R | 1.57 | +0.76R | 2.89 | −3.0 |
| GOOG | 1d | 2,148 | 169 | +0.21R | 1.34 | **+0.45R** | 1.87 | −10.3 |
| GOOG | 1w | 446 | 38 | +0.11R | 1.18 | +0.24R | 1.41 | −3.1 |
| GOOG | 1mo | 104 | 5 | −0.43R | 0.46 | +0.65R | 2.95 | −1.0 |
| BTC/USD | 1mo | 156 | 24 | +0.78R | 3.03 | +0.86R | 3.41 | −1.0 |

Bold marks results with at least 60 trades and positive expectancy in both halves of the sample.

**Across timeframes:**

1. **Shorts lost money on every timeframe tested, 9 out of 9.**
2. **Long-only was positive on all 9.** It held up in both halves of the sample
   on EUR/USD 1h, 2h and 4h and on GOOG daily, which are the only runs with enough
   trades to trust.
3. **Base rules (long and short) are break-even on intraday FX** (1h–4h) and
   negative on 8h. Don't trade them there without dropping shorts.
4. **The 2R target beat the 1R target on 5 of 9**, including every run with
   more than 150 trades. On the smaller samples the results were mixed.
5. **Above 4h the samples get small.** EUR/USD daily has 16 trades and GOOG
   monthly has 5, so treat those rows as anecdotes.
6. **Not tested:** 1m, 5m, 15m and 30m (no sub-hour data was reachable), and
   daily or intraday crypto and gold. Daily EUR/USD bars include short Sunday
   sessions from the hourly source.

Full numbers: [`timeframes.json`](timeframes.json).

## Caveats

- Long-only was chosen *after* seeing these results. It needs confirming on
  data it wasn't picked from, ideally daily BTC/ETH/gold including the
  2018 and 2022 bear markets.
- The BTC result rests on 24 trades, which is too few to rely on.
- Fills assume no slippage beyond the cost figure. Weekend gaps are handled only
  through the next open. Funding and overnight swap fees are not modelled.
- Past results do not predict future results. This is not financial advice.

Full numbers: [`results.json`](results.json).
