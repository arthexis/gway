# file: upgrade.sh

#!/bin/bash
set -e

SNAPSHOT_FILE=".upgrade_snapshot"
ACTION_LOG=".upgrade_action.log"

usage() {
    echo "Usage: $0 [--force] [--auto]"
    echo "  --force    Reinstall and test even if no update is detected."
    echo "  --auto     Revert to previous version automatically if upgrade fails."
    exit 1
}

# --- Parse args ---
FORCE=0
AUTO=0
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        --auto) AUTO=1 ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $arg"; usage ;;
    esac
done

log_action() {
    echo "$(date -Iseconds) | $1" >> "$ACTION_LOG"
}

take_snapshot() {
    local hash
    hash=$(git rev-parse HEAD)
    echo "$hash" > "$SNAPSHOT_FILE"
    # You could also save a pip freeze here if you want to be extra robust
    # pip freeze > .upgrade_requirements.txt
    log_action "Snapshot taken: $hash"
}

restore_snapshot() {
    if [ ! -f "$SNAPSHOT_FILE" ]; then
        echo "No snapshot found! Cannot revert."
        exit 1
    fi
    local hash
    hash=$(cat "$SNAPSHOT_FILE")
    echo "Reverting to previous commit: $hash"
    git reset --hard "$hash"
    git clean -fd
    if [ -d ".venv" ]; then
        source .venv/bin/activate
        pip install -e .
    fi
    log_action "Reverted to: $hash"
}

echo "[1] Taking snapshot of current state..."
take_snapshot

echo "[2] Checking current commit hash..."
OLD_HASH=$(git rev-parse HEAD)

echo "[3] Fetching latest commits from Git..."
git fetch --all --prune

echo "[4] Resetting to origin/main and cleaning up..."
git reset --hard origin/main
git clean -fd

NEW_HASH=$(git rev-parse HEAD)

echo "[5] Ensuring scripts are executable..."
chmod +x *.sh

if [[ "$OLD_HASH" == "$NEW_HASH" && $FORCE -eq 0 ]]; then
    echo "No updates detected. Skipping reinstall (use --force to override)."
    echo "Upgrade script completed."
    exit 0
fi

echo "[6] Activating venv and reinstalling package in editable mode..."
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "Error: .venv directory not found. Did you forget to set up your virtualenv?"
    exit 1
fi

pip install -e .

echo "[7] Running test command..."
if ! gway test; then
    echo "Error: gway test failed after upgrade."
    log_action "Upgrade failed at commit: $NEW_HASH"
    if [[ $AUTO -eq 1 ]]; then
        echo "Auto mode enabled: reverting to previous version."
        restore_snapshot
        echo "Revert completed. Exiting."
        exit 2
    else
        echo "Do you want to revert to the previous version? [Y/n]"
        read -r answer
        if [[ "$answer" =~ ^[Nn] ]]; then
            echo "Leaving the failed version in place."
            log_action "User chose NOT to revert after failed upgrade."
            exit 3
        else
            restore_snapshot
            echo "Revert completed."
            exit 2
        fi
    fi
fi

echo "Upgrade and test completed successfully."
log_action "Upgrade success: $NEW_HASH"
exit 0
