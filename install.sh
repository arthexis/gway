#!/usr/bin/env bash
set -euo pipefail

# It is possible for recipe names to contain slashes, to indicate recipes in sub-folders
# GWAY can handle recipes with slashes, but the service name should clean them up.

# Resolve real directory of this script (even if symlinked)
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
cd "$SCRIPT_DIR"

# 1) Local install: create .venv and install gway
if [[ ! -d ".venv" ]]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
  source .venv/bin/activate
  echo "Installing gway in editable mode..."
  pip install --upgrade pip
  pip install -e .
  deactivate
fi

# Activate the virtual environment
source .venv/bin/activate

# 2) No-arg case: notify installation and usage
if [[ $# -eq 0 ]]; then
  echo "GWAY has been set up in .venv."
  echo "To install a systemd service for a recipe, run:"
  echo "  sudo ./install.sh <recipe-name>"
  deactivate
  exit 0
fi

# 3) Recipe-based service install
RECIPE="$1"
RECIPE_FILE="recipes/${RECIPE}.gwr"
if [[ ! -f "$RECIPE_FILE" ]]; then
  echo "ERROR: Recipe '$RECIPE' not found at $RECIPE_FILE" >&2
  deactivate
  exit 1
fi

# Clean up the service name: replace slashes and illegal chars with '-'
SERVICE_SAFE_RECIPE="${RECIPE//\//-}"
SERVICE_SAFE_RECIPE="${SERVICE_SAFE_RECIPE//[^a-zA-Z0-9_-]/-}"

SERVICE_NAME="gway-${SERVICE_SAFE_RECIPE}.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"

# Determine service user
if [[ -n "${SUDO_USER-}" && "$SUDO_USER" != "root" ]]; then
  SERVICE_USER="$SUDO_USER"
else
  SERVICE_USER="$(whoami)"
fi

echo "Installing systemd service '$SERVICE_NAME' for recipe '$RECIPE'..."

# Backup existing unit
if [[ -f "$SERVICE_PATH" ]]; then
  sudo cp "$SERVICE_PATH" "$SERVICE_PATH.bak.$(date +%s)"
  echo "  → Backed up old unit to $SERVICE_PATH.bak.*"
fi

# Write new unit file
sudo tee "$SERVICE_PATH" > /dev/null <<EOF
[Unit]
Description=GWAY Service ($RECIPE)
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/gway.sh -dr $RECIPE
Restart=on-failure
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo chmod 644 "$SERVICE_PATH"

# Reload, enable & start
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo
sudo systemctl status "$SERVICE_NAME" --no-pager || true

deactivate
