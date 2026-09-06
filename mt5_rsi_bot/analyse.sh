#!/usr/bin/env bash
#
# Backtest a MetaTrader history export in one command.
#
#   ./analyse.sh BTCUSD_M15.csv
#   ./analyse.sh BTCUSD_M15.csv --spread 40      # override the file's spread
#   ./analyse.sh --how                           # how to export from MT5
#
# Builds the virtual environment if needed, runs every strategy and filter
# against the file, does a 70/30 walk forward, and writes a markdown report
# into artifacts/.
#
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

how_to() {
cat <<'HOW'
Exporting bars from MetaTrader 5
--------------------------------

  1. Open a chart for the symbol you trade, on the timeframe you trade
     (for this bot: your MT5_SYMBOL, on MT5_TIMEFRAME).

  2. Scroll back as far as the terminal will go, or press Home. MT5 only
     exports bars it has actually downloaded, so a fresh chart exports almost
     nothing. Tools -> Options -> Charts -> "Max bars in chart" set to
     Unlimited helps.

  3. Right-click the chart -> Save As... (or File -> Save As), and save as CSV.

     The file looks like:
       <DATE>  <TIME>  <OPEN>  <HIGH>  <LOW>  <CLOSE>  <TICKVOL>  <VOL>  <SPREAD>

     The <SPREAD> column is worth having: this tool uses your broker's own
     recorded spread instead of a guess.

  4. Run:  ./analyse.sh path/to/that/file.csv

Free BTC 15-minute history, no account, no terminal
---------------------------------------------------

  Binance publishes its own bars as monthly ZIPs. Download in a browser:

    https://data.binance.vision/?prefix=data/spot/monthly/klines/BTCUSDT/15m/

  Or directly, one month per file:

    https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2025-01.zip

  Change the date for each month you want. A year is 12 files, about 35,000
  bars. Unzip them and either run one at a time, or concatenate first:

    cat BTCUSDT-15m-*.csv > btc_m15.csv
    ./analyse.sh btc_m15.csv --contract-size 1

  These files are headerless with epoch timestamps; the loader reads them as
  they are, no editing needed. Concatenate in date order — though if you get it
  wrong the loader sorts and says so.

  Caveat worth keeping in mind: this is Binance spot BTCUSDT, not your broker's
  BTCUSD CFD. Prices track closely, but the spread and financing are different,
  so it tests the strategy rather than your account. Pass --spread with your
  broker's typical spread to make the costs realistic.

How many bars do you need?
--------------------------
  Enough for the result to mean something. Under 30 trades the tool will say
  so and refuse to draw a conclusion. On M15 that usually means at least a
  year of history — roughly 25,000 bars.

Notes
-----
  * The file's timeframe, decimal places and point size are detected from the
    data. You do not need to tell the tool what they are.
  * A newest-first file is detected and reversed, with a warning.
  * MT5 chart prices are bid. That is what the tool assumes.
HOW
}

for arg in "${@:-}"; do
    case "$arg" in
        --how|--help|-h) how_to; exit 0 ;;
    esac
done

if [ $# -lt 1 ]; then
    echo "usage: ./analyse.sh <export.csv> [extra backtest.py options]" >&2
    echo "       ./analyse.sh --how       # how to export from MT5" >&2
    exit 2
fi

CSV="$1"; shift
if [ ! -f "$CSV" ]; then
    echo "error: no such file: $CSV" >&2
    exit 1
fi

if [ ! -x venv/bin/python ]; then
    echo "Building the virtual environment first..."
    ./run.sh --setup
fi

mkdir -p artifacts
STAMP="$(date -u +%Y%m%d)"
NAME="$(basename "$CSV" | sed 's/\.[^.]*$//')"
OUT="artifacts/SUITE-${NAME}-${STAMP}.md"

exec ./venv/bin/python backtest.py --csv "$CSV" --suite --out "$OUT" "$@"
