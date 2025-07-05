#!/usr/bin/env bash
# file: install.sh
set -euo pipefail

usage() {
  echo "Usage: $0 [--show] [recipe]"
  echo "  --show    List installed gway services"
  exit 0
}

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

# Parse arguments
SHOW=0
RECIPE=""
for arg in "$@"; do
  case "$arg" in
    --show)
      SHOW=1
      ;;
    -h|--help)
      usage
      ;;
    *)
      if [[ -z "$RECIPE" ]]; then
        RECIPE="$arg"
      else
        echo "Unknown argument: $arg" >&2
        deactivate
        exit 1
      fi
      ;;
  esac
done

# No arguments at all -> show instructions
if [[ $SHOW -eq 0 && -z "$RECIPE" ]]; then
  echo "GWAY has been set up in .venv."
  echo "To install a systemd service for a recipe, run:"
  echo "  sudo ./install.sh <recipe-name>"
  echo "Use --show to list installed services"
  deactivate
  exit 0
fi

# Show installed services
if [[ $SHOW -eq 1 && -z "$RECIPE" ]]; then
  echo "Installed GWAY services:" 
  systemctl list-unit-files | grep '^gway-.*\.service' || true
  deactivate
  exit 0
fi

# 3) Recipe-based service install
if [[ -z "$RECIPE" ]]; then
  echo "Error: missing recipe name" >&2
  deactivate
  exit 1
fi

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
ExecStartPre=/home/ubuntu/gway/upgrade.sh --auto
ExecStart=$SCRIPT_DIR/gway.sh -r $RECIPE
Restart=on-failure
RestartSec=10
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
