#!/bin/bash
# file: tools/rpi/setup_nm_install.sh
# Install/remove gway-nm-roles as a user-level systemd timer/service.

SERVICE_NAME="gway-nm-roles"
TARGET_SCRIPT="$HOME/gway/tools/rpi/setup_nm.sh"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SYSTEMD_USER_DIR/$SERVICE_NAME.service"
TIMER_FILE="$SYSTEMD_USER_DIR/$SERVICE_NAME.timer"

set -e

install_service() {
    if [[ ! -x "$TARGET_SCRIPT" ]]; then
        echo "[ERROR] $TARGET_SCRIPT not found or not executable for user $USER."
        exit 1
    fi

    mkdir -p "$SYSTEMD_USER_DIR"

    # Write the user service file
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=GWAY (user): Enforce NM Gateway Roles

[Service]
Type=oneshot
ExecStart=$TARGET_SCRIPT --yes 
EOF

    # Write the user timer file
    cat > "$TIMER_FILE" <<EOF
[Unit]
Description=Run GWAY NM Roles script every 2 minutes (user)

[Timer]
OnBootSec=1min
OnUnitActiveSec=2min
Unit=$SERVICE_NAME.service

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable --now "$SERVICE_NAME.timer"

    echo "[INFO] User service and timer installed & started."
    systemctl --user status "$SERVICE_NAME.timer" --no-pager
}

remove_service() {
    systemctl --user disable --now "$SERVICE_NAME.timer" || true
    rm -f "$SERVICE_FILE" "$TIMER_FILE"
    systemctl --user daemon-reload
    echo "[INFO] User service and timer removed."
}

if [[ "$1" == "--remove" ]]; then
    remove_service
    exit 0
else
    install_service
    exit 0
fi
