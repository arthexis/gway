#!/usr/bin/env bash
# file: install.sh
set -euo pipefail

# Determine sudo usage lazily
SUDO="sudo"

# Resolve real directory of this script (even if symlinked)
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
cd "$SCRIPT_DIR"

# Helper to detect the virtualenv scripts directory across platforms
VENV_DIR=".venv"
VENV_BIN_DIR=""
VENV_CREATED=false

detect_venv_bin_dir() {
  if [[ -d "$VENV_DIR/bin" ]]; then
    VENV_BIN_DIR="$VENV_DIR/bin"
  elif [[ -d "$VENV_DIR/Scripts" ]]; then
    VENV_BIN_DIR="$VENV_DIR/Scripts"
  else
    VENV_BIN_DIR=""
  fi
}

create_virtualenv() {
  echo "Creating virtual environment..."
  python3 -m venv "$VENV_DIR"
  detect_venv_bin_dir
  if [[ -z "$VENV_BIN_DIR" || ! -f "$VENV_BIN_DIR/activate" ]]; then
    echo "ERROR: Unable to locate the virtual environment activation script." >&2
    echo "Tried $VENV_DIR/bin/activate and $VENV_DIR/Scripts/activate." >&2
    echo "Please ensure Python's venv module is available and retry." >&2
    exit 1
  fi
  VENV_CREATED=true
}

ensure_virtualenv() {
  detect_venv_bin_dir
  if [[ ! -f "$VENV_DIR/pyvenv.cfg" ]]; then
    if [[ -d "$VENV_DIR" ]]; then
      echo "Removing incomplete virtual environment..."
      rm -rf "$VENV_DIR"
    fi
    create_virtualenv
    return
  fi

  if [[ -z "$VENV_BIN_DIR" || ! -f "$VENV_BIN_DIR/activate" ]]; then
    echo "Virtual environment activation script missing; recreating..."
    rm -rf "$VENV_DIR"
    create_virtualenv
  fi
}

# 1) Local install: create .venv and install gway if necessary
ensure_virtualenv
if $VENV_CREATED; then
  # shellcheck source=/dev/null
  source "$VENV_BIN_DIR/activate"
  echo "Installing gway in editable mode..."
  pip install --upgrade pip
  pip install -e .
  deactivate
fi

# shellcheck source=/dev/null
source "$VENV_BIN_DIR/activate"

# Parse arguments
DEBUG_FLAG=""
RECIPE=""
FORCE_FLAG=""
ROOT_FLAG=""
REPAIR_FLAG=false
REMOVE_FLAG=false
BIN_FLAG=false
SHELL_FLAG=false
RECIPE_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --repair)
      REPAIR_FLAG=true
      ;;
    --remove)
      REMOVE_FLAG=true
      ;;
    --bin)
      BIN_FLAG=true
      ;;
    --shell)
      SHELL_FLAG=true
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
        RECIPE_ARGS+=("$arg")
      fi
      ;;
  esac
done

# Determine if this action requires root privileges
ROOT_REQUIRED=false
if $REPAIR_FLAG || $REMOVE_FLAG || $BIN_FLAG || $SHELL_FLAG; then
  ROOT_REQUIRED=true
elif [[ -n "$RECIPE" ]]; then
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

if $REPAIR_FLAG && ($REMOVE_FLAG || $BIN_FLAG || $SHELL_FLAG); then
  echo "ERROR: Options --repair, --remove, --bin and --shell are mutually exclusive. Combine --remove with --bin or --shell to uninstall those integrations." >&2
  deactivate
  exit 1
fi

if $BIN_FLAG && $SHELL_FLAG && ! $REMOVE_FLAG; then
  echo "ERROR: Options --bin and --shell cannot be combined unless used with --remove." >&2
  deactivate
  exit 1
fi

if $REPAIR_FLAG && [[ -n "$RECIPE" ]]; then
  echo "ERROR: --repair does not take a recipe argument" >&2
  deactivate
  exit 1
fi

if $SHELL_FLAG && [[ -n "$RECIPE" ]] && ! $REMOVE_FLAG; then
  echo "ERROR: --shell does not take a recipe argument" >&2
  deactivate
  exit 1
fi

if $BIN_FLAG && ! $REMOVE_FLAG && [[ -n "$RECIPE" ]]; then
  echo "ERROR: --bin does not take a recipe argument" >&2
  deactivate
  exit 1
fi

if $REMOVE_FLAG && [[ -z "$RECIPE" ]] && ! $BIN_FLAG && ! $SHELL_FLAG; then
  echo "ERROR: --remove requires a recipe argument" >&2
  deactivate
  exit 1
fi

# Repair previously installed services
if $REPAIR_FLAG; then
  echo "Repairing installed gway services..."
  for unit in /etc/systemd/system/gway-*.service; do
    [[ -f "$unit" ]] || continue
    exec_line=$(grep -E '^ExecStart=' "$unit" | head -n 1)
    if [[ -z "$exec_line" ]]; then
      echo "  Skipping $unit (could not determine ExecStart)" >&2
      continue
    fi

    exec_cmd=${exec_line#ExecStart=}

    mapfile -t exec_parts < <(python3 - <<'PY' -- "$exec_cmd"
import shlex
import sys

for part in shlex.split(sys.argv[1]):
    print(part)
PY
    ) || {
      echo "  Skipping $unit (failed to parse ExecStart)" >&2
      continue
    }

    recipe=""
    args=()
    for ((i = 0; i < ${#exec_parts[@]}; i++)); do
      part="${exec_parts[$i]}"
      if [[ "$part" == "-r" && $((i + 1)) -lt ${#exec_parts[@]} ]]; then
        recipe="${exec_parts[$((i + 1))]}"
        if (( i + 2 < ${#exec_parts[@]} )); then
          args=("${exec_parts[@]:$((i + 2))}")
        fi
        break
      fi
    done

    if [[ -z "$recipe" ]]; then
      echo "  Skipping $unit (could not determine recipe)" >&2
      continue
    fi

    "$SCRIPT_PATH" "$recipe" "${args[@]}"
  done
  deactivate
  exit 0
fi

# Remove specified service
if $REMOVE_FLAG; then
  if [[ -n "$RECIPE" ]]; then
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
  fi
fi

# Install or remove global /usr/bin/gway symlink
if $BIN_FLAG; then
  BIN_TARGET="/usr/bin/gway"
  if $REMOVE_FLAG; then
    echo "Removing gway from $BIN_TARGET..."
    if [[ -L "$BIN_TARGET" ]]; then
      TARGET_PATH="$(readlink -f "$BIN_TARGET")"
      if [[ "$TARGET_PATH" == "$SCRIPT_DIR/gway.sh" ]]; then
        $SUDO rm -f "$BIN_TARGET"
        echo "  → Removed symlink to $TARGET_PATH."
      else
        echo "WARNING: $BIN_TARGET is not managed by this installer; skipping removal." >&2
      fi
    elif [[ -e "$BIN_TARGET" ]]; then
      echo "WARNING: $BIN_TARGET exists but is not a symlink; skipping removal." >&2
    else
      echo "  → No $BIN_TARGET symlink found."
    fi
  else
    echo "Installing gway to $BIN_TARGET..."
    $SUDO ln -sf "$SCRIPT_DIR/gway.sh" "$BIN_TARGET"
    $SUDO chmod +x "$SCRIPT_DIR/gway.sh"
  fi
fi

if ($REMOVE_FLAG || $BIN_FLAG) && ! $SHELL_FLAG; then
  deactivate
  exit 0
fi

# 2) No-arg case: notify installation and usage
if [[ -z "$RECIPE" ]] && ! $REPAIR_FLAG && ! $BIN_FLAG && ! $REMOVE_FLAG && ! $SHELL_FLAG; then
  echo "GWAY has been set up in .venv."
  echo "To install a systemd service for a recipe, run:"
  echo "  sudo ./install.sh <recipe-name> [--debug]"
  echo "To remove a systemd service, run:"
  echo "  sudo ./install.sh <recipe-name> --remove"
  echo "To repair all existing services, run:"
  echo "  sudo ./install.sh --repair"
  echo "To install gway as a global command, run:"
  echo "  sudo ./install.sh --bin"
  echo "To uninstall the global command, run:"
  echo "  sudo ./install.sh --bin --remove"
  echo "To use 'gway shell' as your login shell, run:"
  echo "  sudo ./install.sh --shell"
  echo "To restore your previous login shell, run:"
  echo "  sudo ./install.sh --shell --remove"
  deactivate
  exit 0
fi

SHELL_STATE_FILE="$SCRIPT_DIR/.venv/.gway-shell-default"

# Configure the GWAY login shell wrapper and set it as default
if $SHELL_FLAG; then

  if ! command -v chsh >/dev/null 2>&1; then
    echo "ERROR: 'chsh' command not found. Unable to change default shell." >&2
    deactivate
    exit 1
  fi

  SHELL_WRAPPER="$SCRIPT_DIR/$VENV_BIN_DIR/gway-shell"
  TARGET_USER="${SUDO_USER-$(whoami)}"
  CURRENT_USER="$(whoami)"
  CURRENT_ENTRY="$(getent passwd "$TARGET_USER" || true)"
  CURRENT_SHELL=""
  if [[ -n "$CURRENT_ENTRY" ]]; then
    IFS=':' read -r _ _ _ _ _ _ CURRENT_SHELL <<< "$CURRENT_ENTRY"
  fi

  if $REMOVE_FLAG; then
    echo "Restoring login shell for $TARGET_USER..."
    FALLBACK_SHELL=""
    if [[ -f "$SHELL_STATE_FILE" ]]; then
      FALLBACK_SHELL="$(cat "$SHELL_STATE_FILE")"
    fi
    if [[ -z "$FALLBACK_SHELL" ]]; then
      if command -v bash >/dev/null 2>&1; then
        FALLBACK_SHELL="$(command -v bash)"
      elif [[ -x /bin/sh ]]; then
        FALLBACK_SHELL="/bin/sh"
      else
        echo "ERROR: Unable to determine a fallback shell." >&2
        deactivate
        exit 1
      fi
    fi

    if [[ -n "$CURRENT_SHELL" && "$CURRENT_SHELL" == "$SHELL_WRAPPER" ]]; then
      CHSH_CMD=("chsh" "-s" "$FALLBACK_SHELL")
      if [[ -n "$TARGET_USER" ]]; then
        CHSH_CMD+=("$TARGET_USER")
      fi
      if [[ -n "$SUDO" ]]; then
        CHSH_CMD=("$SUDO" "${CHSH_CMD[@]}")
      fi
      if ! "${CHSH_CMD[@]}"; then
        echo "ERROR: Failed to restore default shell for $TARGET_USER." >&2
        deactivate
        exit 1
      fi
      echo "Default shell for $TARGET_USER restored to '$FALLBACK_SHELL'."
    else
      if [[ -n "$CURRENT_SHELL" ]]; then
        echo "Current shell for $TARGET_USER is '$CURRENT_SHELL'; leaving unchanged."
      else
        echo "WARNING: Unable to determine current shell for $TARGET_USER." >&2
      fi
    fi

    if [[ -f /etc/shells ]]; then
      if grep -Fxq "$SHELL_WRAPPER" /etc/shells; then
        echo "Removing $SHELL_WRAPPER from /etc/shells..."
        if [[ -n "$SUDO" ]]; then
          if ! $SUDO sed -i '\#^'"$SHELL_WRAPPER"'$#d' /etc/shells; then
            echo "WARNING: Failed to update /etc/shells. Please remove '$SHELL_WRAPPER' manually." >&2
          fi
        else
          if ! sed -i '\#^'"$SHELL_WRAPPER"'$#d' /etc/shells; then
            echo "WARNING: Failed to update /etc/shells. Please remove '$SHELL_WRAPPER' manually." >&2
          fi
        fi
      fi
    fi

    if [[ -e "$SHELL_WRAPPER" ]]; then
      if [[ -n "$SUDO" ]]; then
        $SUDO rm -f "$SHELL_WRAPPER"
      else
        rm -f "$SHELL_WRAPPER"
      fi
      echo "Removed shell wrapper at $SHELL_WRAPPER."
    fi

    if [[ -f "$SHELL_STATE_FILE" ]]; then
      if [[ -n "$SUDO" ]]; then
        $SUDO rm -f "$SHELL_STATE_FILE"
      else
        rm -f "$SHELL_STATE_FILE"
      fi
    fi

    deactivate
    exit 0
  fi

  if [[ -n "$CURRENT_SHELL" && "$CURRENT_SHELL" != "$SHELL_WRAPPER" ]]; then
    printf '%s\n' "$CURRENT_SHELL" > "$SHELL_STATE_FILE"
  fi

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

  CHSH_CMD=("chsh" "-s" "$SHELL_WRAPPER")
  if [[ -n "$TARGET_USER" ]]; then
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
GWAY_CMD=("$SCRIPT_DIR/gway.sh")
if [[ -n "$DEBUG_FLAG" ]]; then
  GWAY_CMD+=("$DEBUG_FLAG")
fi
GWAY_CMD+=("-r" "$RECIPE")
if [[ ${#RECIPE_ARGS[@]} -gt 0 ]]; then
  GWAY_CMD+=("${RECIPE_ARGS[@]}")
fi

GWAY_EXEC=""
for part in "${GWAY_CMD[@]}"; do
  if [[ -z "$GWAY_EXEC" ]]; then
    GWAY_EXEC="$(printf '%q' "$part")"
  else
    GWAY_EXEC+=" $(printf '%q' "$part")"
  fi
done

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
