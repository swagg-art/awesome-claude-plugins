# Testing on your own M15 history

Everything so far has been measured on BTC/USD **daily** bars, because that is
the data that could be obtained without a paid feed. The bot is configured for
**M15**. This is how to close that gap, and one finding worth acting on that
came out of building it.

## The finding: the default is not the configuration that was reported best

The v2 report headlines the confirmed strategy at **37 trades, PF 1.193,
+$188.87**. That was measured with divergence-only arming. The shipped default
is `DIVERGENCE_ONLY=false`, which is a different, measurably worse
configuration:

| Arming mode | Trades | Win% | Profit factor | Net | Out-of-sample net |
| --- | ---: | ---: | ---: | ---: | ---: |
| `DIVERGENCE_ONLY=false` (**current default**) | 48 | 22.9 | 1.068 | +$85.45 | +$126.08 |
| `DIVERGENCE_ONLY=true` (**what the report headlines**) | 37 | 29.7 | **1.193** | **+$188.87** | **+$148.90** |

Divergence-only is better on both halves of the split. The default has not been
changed here, because flipping a trading default is your call, not a side effect
of adding a tool. The suite now prints both rows every run, so the two can never
diverge silently again.

## Where to get M15 data

Two sources. The second needs nothing installed.

### Binance public dumps — free, no account, no terminal

Binance publishes its own bars as monthly ZIP files, downloadable in a browser:

    https://data.binance.vision/?prefix=data/spot/monthly/klines/BTCUSDT/15m/

One file per month, roughly 2,900 bars each. A year is 12 files and about
35,000 bars — an order of magnitude more evidence than the 3,170 daily bars
everything so far rests on.

```
unzip 'BTCUSDT-15m-*.zip'
cat BTCUSDT-15m-*.csv > btc_m15.csv
./analyse.sh btc_m15.csv --spread 40
```

The files are headerless with epoch timestamps (milliseconds on older ones,
microseconds on some 2025 files). The loader reads all of those variants as
they are — no editing, no header to add.

**The caveat:** this is Binance spot BTCUSDT, not your broker's BTCUSD CFD.
Prices track closely, but spread and financing differ, so it tests *the
strategy* rather than *your account*. Pass `--spread` with your broker's typical
spread so the costs are at least realistic.

### Your broker's own export

See below. More accurate to what you would actually trade, but it needs MT5
installed and the history downloaded into the terminal first.

## Running it

```
./analyse.sh path/to/BTCUSD_M15.csv
```

That builds the environment if needed, runs every strategy and filter against
the file, does a 70/30 walk forward, prints the tables, and writes
`artifacts/SUITE-<name>-<date>.md`.

`./analyse.sh --how` prints the export steps.

## Exporting from MetaTrader 5

1. Open a chart for your symbol on your timeframe.
2. Press Home and let it load. **MT5 only exports bars it has downloaded**, so
   a freshly opened chart exports almost nothing. Tools → Options → Charts →
   "Max bars in chart" → Unlimited.
3. Right-click the chart → Save As → CSV.
4. Run `./analyse.sh` on the file.

The export looks like:

```
<DATE>  <TIME>  <OPEN>  <HIGH>  <LOW>  <CLOSE>  <TICKVOL>  <VOL>  <SPREAD>
```

The `<SPREAD>` column is the useful part — the tool uses your broker's own
recorded spread rather than a guess. Nothing needs to be configured: timeframe,
decimal places, point size and spread are all read from the file.

## How much history

Enough that the answer means something. Under 30 trades the suite refuses to
draw a conclusion and says so. On M15 that is usually a year or more — roughly
25,000 bars.

For scale: on daily bars, 8.5 years produced only 37 trades. This strategy is
selective, which is a virtue in trading and a problem for measuring it. M15
should generate many more trades over far less calendar time, which is the real
reason the M15 test matters — it is the first chance to get a sample size worth
believing.

## What the loader protects you from

Real exports are messy, and a backtest that quietly accepts a broken file is
worse than one that fails. The loader detects and reports:

- **A newest-first file** — reversed, with a warning. Silently running history
  backwards would produce confident nonsense.
- **Duplicate timestamps** — dropped.
- **Impossible bars** (high below low, or outside the open/close range) —
  dropped and counted.
- **Repeated headers, blank lines, footers** — skipped and counted.
- **A timeframe that disagrees with `MT5_TIMEFRAME`** — flagged; the file wins.
- **Gaps longer than three bars** — counted, since they are normal over FX
  weekends and suspicious otherwise.
- **Too little history** — refused outright rather than reported on.

Nine tests in `test_backtest.py` cover these against files written in
MetaTrader's actual export format.

## What to do with the result

Read the **out-of-sample** column. A variant that wins in sample and loses out
of sample is fitted to the past, and the suite says so in its verdict.

If M15 shows the confirmed strategy positive in and out of sample over a
reasonable number of trades, that is the first genuine evidence in this project
that there is something here. If it does not, the honest conclusion is that the
strategy does not work, and the value of the project is the tooling: the safety
layer, the daily loss guard, and a backtester that tells you the truth.
