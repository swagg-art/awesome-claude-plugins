#!/usr/bin/env bash
#
# Installs the bot as a systemd daemon.
#
#   ./deploy_service.sh              install and enable
#   ./deploy_service.sh --start      install, enable and start now
#   ./deploy_service.sh --uninstall  stop, disable and remove
#   ./deploy_service.sh --print      show the unit file and change nothing
#
set -euo pipefail

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
SERVICE_NAME="rsibot"
UNIT="/etc/systemd/system/${SERVICE_NAME}.service"

# whoami returns root when this script is itself run under sudo, which would
# silently install a root-owned service holding broker credentials. SUDO_USER
# is the human who invoked it.
RUN_AS="${SUDO_USER:-$(whoami)}"

ACTION="install"
for arg in "${@:-}"; do
    case "$arg" in
        --start)     START_NOW=1 ;;
        --uninstall) ACTION="uninstall" ;;
        --print)     ACTION="print" ;;
        "")          ;;
        -h|--help)   sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

if ! command -v systemctl >/dev/null 2>&1; then
    echo "error: systemctl not found — this host does not use systemd." >&2
    echo "Run the bot with ./run.sh instead." >&2
    exit 1
fi

unit_body() {
cat <<EOF
[Unit]
Description=MetaTrader 5 Native RSI Bot Daemon
After=network-online.target
Wants=network-online.target

# Without these systemd restarts a misconfigured bot every 10 seconds forever.
# They belong in [Unit]; under [Service] they are silently ignored.
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=${RUN_AS}
WorkingDirectory=${DIR}
ExecStart=${DIR}/venv/bin/python ${DIR}/main.py
Environment=PYTHONUNBUFFERED=1

Restart=always
RestartSec=10

# The bot handles SIGTERM: it finishes the cycle, calls mt5.shutdown() and
# exits. Give it room rather than killing it mid-order.
KillSignal=SIGTERM
TimeoutStopSec=45

StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=${DIR}

[Install]
WantedBy=multi-user.target
EOF
}

if [ "$ACTION" = "print" ]; then
    unit_body
    exit 0
fi

if [ "$ACTION" = "uninstall" ]; then
    echo "This will stop and remove ${SERVICE_NAME}.service."
    read -r -p "Continue? [y/N] " reply
    case "$reply" in [Yy]*) ;; *) echo "aborted."; exit 1 ;; esac
    sudo systemctl stop "${SERVICE_NAME}.service" 2>/dev/null || true
    sudo systemctl disable "${SERVICE_NAME}.service" 2>/dev/null || true
    sudo rm -f "$UNIT"
    sudo systemctl daemon-reload
    echo "Removed. Your .env and venv were left alone."
    exit 0
fi

# --- preflight -------------------------------------------------------------
# A unit pointing at a venv that does not exist fails on every restart.
if [ ! -x "${DIR}/venv/bin/python" ]; then
    echo "No virtual environment yet — building it first."
    "${DIR}/run.sh" --setup
fi

if [ ! -f "${DIR}/.env" ]; then
    echo "error: no .env file. Copy .env.example to .env and edit it first." >&2
    exit 1
fi

if grep -q '^MT5_PASSWORD=YourPasswordHere' "${DIR}/.env"; then
    echo "error: .env still contains the placeholder password." >&2
    exit 1
fi

dry_run="$(grep -E '^DRY_RUN=' "${DIR}/.env" | tail -1 | cut -d= -f2- || true)"
symbol="$(grep -E '^MT5_SYMBOL=' "${DIR}/.env" | tail -1 | cut -d= -f2- || true)"

echo
echo "About to install a systemd service:"
echo
echo "  unit      ${UNIT}"
echo "  runs as   ${RUN_AS}"
echo "  command   ${DIR}/venv/bin/python ${DIR}/main.py"
echo "  symbol    ${symbol:-unset}"
echo "  dry run   ${dry_run:-false}"
echo "  restart   always, 10s apart, giving up after 5 failures in 5 minutes"
echo
if [ "${dry_run:-false}" != "true" ]; then
    echo "  WARNING: this service will place REAL orders, unattended, on every boot."
    echo
    read -r -p "  Type 'trade' to continue: " confirm
    [ "$confirm" = "trade" ] || { echo "aborted."; exit 1; }
else
    read -r -p "Continue? [y/N] " reply
    case "$reply" in [Yy]*) ;; *) echo "aborted."; exit 1 ;; esac
fi

echo "Creating systemd daemon service..."
unit_body | sudo tee "$UNIT" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"
echo "Service ${SERVICE_NAME}.service configured and enabled."

if [ "${START_NOW:-0}" = "1" ]; then
    sudo systemctl restart "${SERVICE_NAME}.service"
    sleep 2
    if sudo systemctl is-active --quiet "${SERVICE_NAME}.service"; then
        echo "Service started."
    else
        echo "Service failed to stay up. Recent log:" >&2
        sudo journalctl -u "${SERVICE_NAME}" -n 30 --no-pager >&2 || true
        exit 1
    fi
else
    echo "To launch immediately run: sudo systemctl start ${SERVICE_NAME}"
fi

echo
echo "  logs    sudo journalctl -u ${SERVICE_NAME} -f"
echo "  stop    sudo systemctl stop ${SERVICE_NAME}"
echo "  remove  ./deploy_service.sh --uninstall"
