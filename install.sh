#!/usr/bin/env bash
# file: install.sh
set -euo pipefail

# Determine sudo usage lazily
SUDO="sudo"

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
ROOT_FLAG=""
for arg in "$@"; do
  case "$arg" in
    --repair)
      ACTION="repair"
      ;;
    --remove)
      ACTION="remove"
      ;;
    --bin)
      ACTION="bin"
      ;;
    --shell)
      ACTION="shell"
      ;;
    --force)
      FORCE_FLAG="--force"
      ;;
    --debug)
      DEBUG_FLAG="-d"
      ;;
    --root)
      ROOT_FLAG="--root"
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

# Determine if this action requires root privileges
ROOT_REQUIRED=false
if [[ "$ACTION" == "remove" || "$ACTION" == "repair" || "$ACTION" == "bin" || "$ACTION" == "shell" ]]; then
  ROOT_REQUIRED=true
elif [[ "$ACTION" == "install" && -n "$RECIPE" ]]; then
  ROOT_REQUIRED=true
fi

if $ROOT_REQUIRED; then
  if [[ $EUID -eq 0 ]]; then
    SUDO=""
  else
    if command -v sudo >/dev/null 2>&1; then
      SUDO="sudo"
    else
      echo "ERROR: This operation requires root privileges via sudo." >&2
      echo "Please install sudo or re-run this script as root." >&2
      deactivate
      exit 1
    fi
  fi
fi

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
  $SUDO systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  $SUDO systemctl disable "$SERVICE_NAME" 2>/dev/null || true
  if [[ -f "$SERVICE_PATH" ]]; then
    $SUDO rm -f "$SERVICE_PATH"
  fi
  $SUDO systemctl daemon-reload
  deactivate
  exit 0
fi

# Install global /usr/bin/gway symlink
if [[ "$ACTION" == "bin" ]]; then
  if [[ -n "$RECIPE" ]]; then
    echo "ERROR: --bin does not take a recipe argument" >&2
    deactivate
    exit 1
  fi
  echo "Installing gway to /usr/bin/gway..."
  $SUDO ln -sf "$SCRIPT_DIR/gway.sh" /usr/bin/gway
  $SUDO chmod +x "$SCRIPT_DIR/gway.sh"
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
  echo "To install gway as a global command, run:"
  echo "  sudo ./install.sh --bin"
  echo "To use 'gway shell' as your login shell, run:"
  echo "  sudo ./install.sh --shell"
  deactivate
  exit 0
fi

# Configure the GWAY login shell wrapper and set it as default
if [[ "$ACTION" == "shell" ]]; then
  if [[ -n "$RECIPE" ]]; then
    echo "ERROR: --shell does not take a recipe argument" >&2
    deactivate
    exit 1
  fi

  if ! command -v chsh >/dev/null 2>&1; then
    echo "ERROR: 'chsh' command not found. Unable to change default shell." >&2
    deactivate
    exit 1
  fi

  SHELL_WRAPPER="$SCRIPT_DIR/.venv/bin/gway-shell"
  cat > "$SHELL_WRAPPER" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"

exec "$SCRIPT_DIR/gway" shell "$@"
EOF

  chmod +x "$SHELL_WRAPPER"

  if [[ -f /etc/shells ]]; then
    if ! grep -Fxq "$SHELL_WRAPPER" /etc/shells; then
      echo "Registering $SHELL_WRAPPER in /etc/shells..."
      if [[ -n "$SUDO" ]]; then
        if ! echo "$SHELL_WRAPPER" | $SUDO tee -a /etc/shells > /dev/null; then
          echo "ERROR: Failed to update /etc/shells. Please add '$SHELL_WRAPPER' manually." >&2
          deactivate
          exit 1
        fi
      else
        if ! echo "$SHELL_WRAPPER" | tee -a /etc/shells > /dev/null; then
          echo "ERROR: Failed to update /etc/shells. Please add '$SHELL_WRAPPER' manually." >&2
          deactivate
          exit 1
        fi
      fi
    fi
  else
    echo "WARNING: /etc/shells not found; skipping registration." >&2
  fi

  TARGET_USER="${SUDO_USER-$(whoami)}"
  CURRENT_USER="$(whoami)"
  CHSH_CMD=("chsh" "-s" "$SHELL_WRAPPER")
  if [[ "$TARGET_USER" != "$CURRENT_USER" ]]; then
    CHSH_CMD+=("$TARGET_USER")
  fi
  if [[ -n "$SUDO" ]]; then
    CHSH_CMD=("$SUDO" "${CHSH_CMD[@]}")
  fi

  if ! "${CHSH_CMD[@]}"; then
    echo "ERROR: Failed to set default shell for $TARGET_USER." >&2
    deactivate
    exit 1
  fi

  echo "Default shell for $TARGET_USER set to '$SHELL_WRAPPER'."
  echo "The system will launch 'gway shell' on the next login."

  deactivate
  exit 0
fi

# 3) Recipe-based service install
# Resolve recipe filename similar to gway's internal lookup
find_recipe_file() {
  local recipe="$1"
  # Absolute path provided
  if [[ "$recipe" = /* && -f "$recipe" ]]; then
    echo "$recipe"
    return 0
  fi

  local base_names=()
  base_names+=("$recipe")
  if [[ "$recipe" == *.* ]]; then
    base_names+=("${recipe//./_}")
    base_names+=("${recipe//./\/}")
  fi

  declare -A seen
  local candidates=()
  for base in "${base_names[@]}"; do
    if [[ -z "${seen[$base]+x}" ]]; then
      candidates+=("$base")
      seen[$base]=1
    fi
    if [[ "$base" != *.* ]]; then
      for ext in ".gwr" ".txt"; do
        local name="$base$ext"
        if [[ -z "${seen[$name]+x}" ]]; then
          candidates+=("$name")
          seen[$name]=1
        fi
      done
    fi
  done

  for name in "${candidates[@]}"; do
    local path="recipes/$name"
    if [[ -f "$path" ]]; then
      echo "$path"
      return 0
    fi
  done
  return 1
}

RECIPE_FILE=$(find_recipe_file "$RECIPE") || {
  echo "ERROR: Recipe '$RECIPE' not found in recipes/" >&2
  deactivate
  exit 1
}

# Clean up the service name: replace slashes and illegal chars with '-'
SERVICE_SAFE_RECIPE="${RECIPE//\//-}"
SERVICE_SAFE_RECIPE="${SERVICE_SAFE_RECIPE//[^a-zA-Z0-9_-]/-}"

SERVICE_NAME="gway-${SERVICE_SAFE_RECIPE}.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"

# Determine service user
if [[ "$ROOT_FLAG" == "--root" ]]; then
  SERVICE_USER="root"
elif [[ -n "${SUDO_USER-}" && "$SUDO_USER" != "root" ]]; then
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
  $SUDO cp "$SERVICE_PATH" "$SERVICE_PATH.bak.$(date +%s)"
  echo "  → Backed up old unit to $SERVICE_PATH.bak.*"
fi

# Write new unit file
$SUDO tee "$SERVICE_PATH" > /dev/null <<EOF
[Unit]
Description=GWAY Service ($RECIPE)
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$SCRIPT_DIR
ExecStartPre=/usr/bin/env bash $SCRIPT_DIR/upgrade.sh
ExecStart=$GWAY_EXEC
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

$SUDO chmod 644 "$SERVICE_PATH"

# Reload, enable & start
$SUDO systemctl daemon-reload
$SUDO systemctl enable "$SERVICE_NAME"
$SUDO systemctl restart "$SERVICE_NAME"

echo
$SUDO systemctl status "$SERVICE_NAME" --no-pager || true

deactivate
