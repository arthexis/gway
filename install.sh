#!/usr/bin/env bash
# file: install.sh
set -euo pipefail

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
ACTION="install"
DEBUG_FLAG=""
RECIPE=""
FORCE_FLAG=""
for arg in "$@"; do
  case "$arg" in
    --repair)
      ACTION="repair"
      ;;
    --remove)
      ACTION="remove"
      ;;
    --force)
      FORCE_FLAG="--force"
      ;;
    --debug)
      DEBUG_FLAG="-d"
      ;;
    *)
      if [[ -z "$RECIPE" ]]; then
        RECIPE="$arg"
      else
        echo "ERROR: Unexpected argument $arg" >&2
        deactivate
        exit 1
      fi
      ;;
  esac
done

# Repair previously installed services
if [[ "$ACTION" == "repair" ]]; then
  if [[ -n "$RECIPE" ]]; then
    echo "ERROR: --repair does not take a recipe argument" >&2
    deactivate
    exit 1
  fi
  echo "Repairing installed gway services..."
  for unit in /etc/systemd/system/gway-*.service; do
    [[ -f "$unit" ]] || continue
    recipe=$(grep -oE 'ExecStart=.*-r ([^ ]+)' "$unit" | awk '{print $2}')
    if [[ -z "$recipe" ]]; then
      echo "  Skipping $unit (could not determine recipe)" >&2
      continue
    fi
    "$SCRIPT_PATH" "$recipe"
  done
  deactivate
  exit 0
fi

# Remove specified service
if [[ "$ACTION" == "remove" ]]; then
  if [[ -z "$RECIPE" ]]; then
    echo "ERROR: --remove requires a recipe argument" >&2
    deactivate
    exit 1
  fi
  SERVICE_SAFE_RECIPE="${RECIPE//\//-}"
  SERVICE_SAFE_RECIPE="${SERVICE_SAFE_RECIPE//[^a-zA-Z0-9_-]/-}"
  SERVICE_NAME="gway-${SERVICE_SAFE_RECIPE}.service"
  SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
  echo "Removing systemd service '$SERVICE_NAME' for recipe '$RECIPE'..."
  sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  sudo systemctl disable "$SERVICE_NAME" 2>/dev/null || true
  if [[ -f "$SERVICE_PATH" ]]; then
    sudo rm -f "$SERVICE_PATH"
  fi
  sudo systemctl daemon-reload
  deactivate
  exit 0
fi

# 2) No-arg case: notify installation and usage
if [[ -z "$RECIPE" && "$ACTION" == "install" ]]; then
  echo "GWAY has been set up in .venv."
  echo "To install a systemd service for a recipe, run:"
  echo "  sudo ./install.sh <recipe-name> [--debug]"
  echo "To remove a systemd service, run:"
  echo "  sudo ./install.sh <recipe-name> --remove"
  echo "To repair all existing services, run:"
  echo "  sudo ./install.sh --repair"
  deactivate
  exit 0
fi

# 3) Recipe-based service install
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

# Build ExecStart command
GWAY_EXEC="$SCRIPT_DIR/gway.sh"
if [[ -n "$DEBUG_FLAG" ]]; then
  GWAY_EXEC+=" $DEBUG_FLAG"
fi
GWAY_EXEC+=" -r $RECIPE"

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
ExecStartPre=$SCRIPT_DIR/upgrade.sh --auto
ExecStart=$GWAY_EXEC
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
