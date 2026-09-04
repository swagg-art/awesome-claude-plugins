#!/usr/bin/env bash
#
# Local runner: creates the virtual environment if it is missing, installs
# dependencies when they have changed, loads .env, and starts the bot in the
# foreground. Safe to run repeatedly.
#
#   ./run.sh              start the bot
#   ./run.sh --setup      build the environment and stop
#   ./run.sh --dry-run    force MT5_RSI_DRY_RUN=true for this run only
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

VENV="$HERE/.venv"
STAMP="$VENV/.requirements-stamp"

setup_only=false
for arg in "$@"; do
  case "$arg" in
    --setup)   setup_only=true ;;
    --dry-run) export MT5_RSI_DRY_RUN=true ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# --- python ----------------------------------------------------------------
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: $PYTHON not found. Install Python 3.11 or newer." >&2
  exit 1
fi

version="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "error: Python 3.11+ required, found $version." >&2
  exit 1
fi

# --- virtual environment ---------------------------------------------------
if [[ ! -d "$VENV" ]]; then
  echo "creating virtual environment in .venv (Python $version)"
  "$PYTHON" -m venv "$VENV"
fi

# Reinstall only when requirements.txt has changed since the last successful
# install, so a normal start does not wait on pip.
if [[ ! -f "$STAMP" ]] || ! cmp -s requirements.txt "$STAMP"; then
  echo "installing dependencies"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r requirements.txt
  cp requirements.txt "$STAMP"
else
  echo "dependencies up to date"
fi

if [[ "$setup_only" == true ]]; then
  echo "setup complete. Start the bot with: ./run.sh"
  exit 0
fi

# --- configuration ---------------------------------------------------------
if [[ ! -f .env ]]; then
  echo
  echo "no .env found. Creating one from .env.example — it defaults to the"
  echo "mock adapter in paper mode, so it is safe to start as-is."
  echo
  cp .env.example .env
fi

# Export everything defined in .env for the child process.
set -a
# shellcheck disable=SC1091
source .env
set +a

if [[ "${NATIVE_MT5_MODE:-}" == "live" && "${MT5_RSI_DRY_RUN:-false}" != "true" ]]; then
  echo
  echo "  NATIVE_MT5_MODE=live — this will place real orders with real money."
  echo "  Symbol: ${MT5_RSI_SYMBOL:-EURUSD}   Risk: ${MT5_RSI_RISK_PCT:-0.5}%/trade"
  echo
  read -r -p "  Type 'live' to continue: " confirm
  [[ "$confirm" == "live" ]] || { echo "aborted."; exit 1; }
fi

echo "starting — Ctrl-C to stop"
exec "$VENV/bin/python" main.py
