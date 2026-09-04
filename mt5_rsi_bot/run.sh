#!/usr/bin/env bash
#
# Local runner. Creates the virtual environment, installs dependencies when
# requirements.txt has changed, and launches the bot.
#
#   ./run.sh             start the bot
#   ./run.sh --setup     build the environment and stop
#   ./run.sh --dry-run   force DRY_RUN=true for this run only
#
set -euo pipefail

# systemd and cron do not run this from its own directory.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

STAMP="venv/.requirements-stamp"

for arg in "${@:-}"; do
    case "$arg" in
        --setup)   SETUP_ONLY=1 ;;
        --dry-run) export DRY_RUN=true ;;
        "")        ;;
        -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    echo "error: Python 3.10 or newer is required." >&2
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "Initializing Virtual Environment..."
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
fi

# The original only installed when the venv was absent, so an edit to
# requirements.txt was never picked up. Compare against a stamp instead.
if [ ! -f "$STAMP" ] || ! cmp -s requirements.txt "$STAMP"; then
    echo "Installing dependencies..."
    ./venv/bin/pip install -r requirements.txt
    cp requirements.txt "$STAMP"
fi

if [ "${SETUP_ONLY:-0}" = "1" ]; then
    echo "Setup complete. Start with: ./run.sh"
    exit 0
fi

if [ ! -f ".env" ]; then
    echo "Creating .env configuration file from template..."
    cp .env.example .env
    echo
    echo "IMPORTANT: .env still holds the placeholder credentials from the"
    echo "template. Edit it before running the bot."
    exit 1
fi

# Refuse to start on the shipped placeholders — they would otherwise reach
# mt5.login() and fail with a confusing broker error.
if grep -q '^MT5_PASSWORD=YourPasswordHere' .env; then
    echo "error: .env still contains the placeholder password." >&2
    echo "Edit .env with your real broker credentials first." >&2
    exit 1
fi

if [ "${DRY_RUN:-false}" != "true" ]; then
    symbol="$(grep -E '^MT5_SYMBOL=' .env | tail -1 | cut -d= -f2- || true)"
    lots="$(grep -E '^LOT_SIZE=' .env | tail -1 | cut -d= -f2- || true)"
    echo
    echo "  This places REAL orders: ${symbol:-?} at ${lots:-?} lots per entry."
    echo "  Set DRY_RUN=true in .env to watch it first."
    echo
    read -r -p "  Type 'trade' to continue: " confirm
    [ "$confirm" = "trade" ] || { echo "aborted."; exit 1; }
fi

echo "Launching MT5 RSI Bot..."
exec ./venv/bin/python main.py
