#!/usr/bin/env bash
#
# Installs the bot as a systemd service so it survives reboots and restarts on
# crash.
#
#   ./deploy_service.sh                install and start a user service
#   ./deploy_service.sh --system       install system-wide (needs sudo)
#   ./deploy_service.sh --uninstall    stop, disable and remove the unit
#   ./deploy_service.sh --print        show the unit file and exit, change nothing
#
# A user service is the default and the better choice: no root, and it is
# confined to your account. It only runs while you are logged in unless you
# enable lingering, which this script offers to do.
#
# Note on platforms: systemd is Linux, while the MetaTrader5 Python package is
# Windows-only. A Linux deployment therefore runs either against the mock
# adapter, or against a terminal under Wine. Check your .env before assuming
# this is trading anything real.
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

SERVICE="mt5-rsi-bot"
UNIT="$SERVICE.service"

scope="user"
action="install"
for arg in "$@"; do
  case "$arg" in
    --system)    scope="system" ;;
    --user)      scope="user" ;;
    --uninstall) action="uninstall" ;;
    --print)     action="print" ;;
    -h|--help)   sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if ! command -v systemctl >/dev/null 2>&1; then
  echo "error: systemctl not found — this host does not use systemd." >&2
  echo "Run the bot with ./run.sh, or use your platform's own service manager." >&2
  exit 1
fi

if [[ "$scope" == "user" ]]; then
  SYSTEMCTL=(systemctl --user)
  UNIT_DIR="$HOME/.config/systemd/user"
  JOURNAL=(journalctl --user -u "$SERVICE")
else
  SYSTEMCTL=(sudo systemctl)
  UNIT_DIR="/etc/systemd/system"
  JOURNAL=(sudo journalctl -u "$SERVICE")
fi

write_unit() {
  cat <<UNIT_BODY
[Unit]
Description=MT5 RSI bot ($SERVICE)
After=network-online.target
Wants=network-online.target

# If it crashes five times in five minutes the configuration is wrong, not the
# network. Give up rather than loop forever. These belong in [Unit]: systemd
# silently ignores them under [Service].
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
WorkingDirectory=$HERE
EnvironmentFile=$HERE/.env
ExecStart=$HERE/.venv/bin/python $HERE/main.py

# The bot handles SIGTERM: it finishes the current cycle, closes the broker
# session and exits. Give it room to do that rather than killing it mid-order.
KillSignal=SIGTERM
TimeoutStopSec=45

Restart=always
RestartSec=15

StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE

# Least privilege: the bot needs its own directory and the network, nothing else.
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$HERE
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true

[Install]
WantedBy=$([[ "$scope" == "user" ]] && echo "default.target" || echo "multi-user.target")
UNIT_BODY
}

# --- print -----------------------------------------------------------------
if [[ "$action" == "print" ]]; then
  write_unit
  exit 0
fi

# --- uninstall -------------------------------------------------------------
if [[ "$action" == "uninstall" ]]; then
  echo "This will stop and remove the $scope service '$SERVICE'."
  read -r -p "Continue? [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]] || { echo "aborted."; exit 1; }

  "${SYSTEMCTL[@]}" stop "$UNIT" 2>/dev/null || true
  "${SYSTEMCTL[@]}" disable "$UNIT" 2>/dev/null || true
  if [[ "$scope" == "user" ]]; then
    rm -f "$UNIT_DIR/$UNIT"
  else
    sudo rm -f "$UNIT_DIR/$UNIT"
  fi
  "${SYSTEMCTL[@]}" daemon-reload
  echo "removed. Your .env and .venv were left alone."
  exit 0
fi

# --- preflight -------------------------------------------------------------
if [[ ! -x .venv/bin/python ]]; then
  echo "no virtual environment yet — building it first"
  ./run.sh --setup
fi

if [[ ! -f .env ]]; then
  echo "error: no .env file. Copy .env.example to .env and edit it first." >&2
  exit 1
fi

# systemd's EnvironmentFile parser is not a shell: it does not expand variables
# and chokes on 'export'. Catch that here rather than at first boot.
if grep -qE '^\s*export\s' .env; then
  echo "error: .env contains 'export' lines, which systemd cannot parse." >&2
  echo "Use plain KEY=value lines." >&2
  exit 1
fi

# shellcheck disable=SC1091
mode="$(grep -E '^\s*NATIVE_MT5_MODE=' .env | tail -1 | cut -d= -f2- | tr -d '[:space:]')"

echo
echo "About to install a $scope systemd service:"
echo
echo "  unit       $UNIT_DIR/$UNIT"
echo "  runs       $HERE/.venv/bin/python $HERE/main.py"
echo "  env from   $HERE/.env"
echo "  mode       ${mode:-unset}"
echo "  restart    always, 15s apart, giving up after 5 failures in 5 minutes"
echo
if [[ "$mode" == "live" ]]; then
  echo "  WARNING: NATIVE_MT5_MODE=live — this service will place real orders,"
  echo "  unattended, every time this machine boots."
  echo
  read -r -p "  Type 'live' to continue: " confirm
  [[ "$confirm" == "live" ]] || { echo "aborted."; exit 1; }
else
  read -r -p "Continue? [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]] || { echo "aborted."; exit 1; }
fi

# --- install ---------------------------------------------------------------
if [[ "$scope" == "user" ]]; then
  mkdir -p "$UNIT_DIR"
  write_unit > "$UNIT_DIR/$UNIT"
else
  write_unit | sudo tee "$UNIT_DIR/$UNIT" >/dev/null
fi

"${SYSTEMCTL[@]}" daemon-reload
"${SYSTEMCTL[@]}" enable "$UNIT"
"${SYSTEMCTL[@]}" restart "$UNIT"

sleep 2
if ! "${SYSTEMCTL[@]}" is-active --quiet "$UNIT"; then
  echo
  echo "the service did not stay up. Recent log:" >&2
  "${JOURNAL[@]}" -n 30 --no-pager >&2 || true
  exit 1
fi

echo
echo "$SERVICE is running."
echo
echo "  logs      ${JOURNAL[*]} -f"
echo "  status    ${SYSTEMCTL[*]} status $UNIT"
echo "  stop      ${SYSTEMCTL[*]} stop $UNIT"
echo "  remove    ./deploy_service.sh --uninstall$([[ "$scope" == "system" ]] && echo ' --system')"

if [[ "$scope" == "user" ]] && ! loginctl show-user "$USER" 2>/dev/null | grep -q 'Linger=yes'; then
  echo
  echo "Note: a user service stops when you log out. To keep it running:"
  echo "  sudo loginctl enable-linger $USER"
fi
