#!/bin/bash
# file: setup_nm_service.sh
# Manage installation/removal of gway-nm-roles systemd timer and service.

TARGET_SCRIPT="/home/arthe/gway/tools/rpi/setup_nm.sh"
SERVICE_NAME="gway-nm-roles"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME.service"
TIMER_PATH="/etc/systemd/system/$SERVICE_NAME.timer"

set -e

function install_service {
    if [[ ! -x "$TARGET_SCRIPT" ]]; then
        echo "[ERROR] $TARGET_SCRIPT is not found or not executable."
        exit 1
    fi

    # Create the service file
    sudo tee "$SERVICE_PATH" > /dev/null <<EOF
[Unit]
Description=GWAY: Enforce NM Gateway Roles

[Service]
Type=oneshot
ExecStart=$TARGET_SCRIPT --yes --force
EOF

    # Create the timer file
    sudo tee "$TIMER_PATH" > /dev/null <<EOF
[Unit]
Description=Run GWAY NM Roles script every 2 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=2min
Unit=$SERVICE_NAME.service

[Install]
WantedBy=timers.target
EOF

    # Reload, enable, start
    sudo systemctl daemon-reload
    sudo systemctl enable --now "$SERVICE_NAME.timer"
    echo "[INFO] Service and timer installed. Status:"
    systemctl status "$SERVICE_NAME.timer" --no-pager
}

function remove_service {
    sudo systemctl disable --now "$SERVICE_NAME.timer" || true
    sudo rm -f "$SERVICE_PATH" "$TIMER_PATH"
    sudo systemctl daemon-reload
    echo "[INFO] Service and timer removed."
}

if [[ "$1" == "--remove" ]]; then
    remove_service
    exit 0
else
    install_service
    exit 0
fi
