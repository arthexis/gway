#!/bin/bash
# file: upgrade.sh

set -e

SNAPSHOT_FILE=".upgrade_snapshot"
ACTION_LOG=".upgrade_action.log"

usage() {
    echo "Usage: $0 [--force] [--auto]"
    echo "  --force    Reinstall and test even if no update is detected."
    echo "  --auto     Revert to previous version automatically if upgrade fails."
    exit 0
}

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
    log_action "Snapshot taken: $hash"
}

restore_snapshot() {
    if [ ! -f "$SNAPSHOT_FILE" ]; then
        echo "No snapshot found! Cannot revert."
        log_action "No snapshot found: revert skipped."
        return 1
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
    return 0
}

auto_exit_success() {
    echo "Exiting successfully (auto mode)."
    exit 0
}

echo "[1] Taking snapshot of current state..."
take_snapshot || true

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
    auto_exit_success
fi

echo "[6] Activating venv and reinstalling package in editable mode..."
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "Error: .venv directory not found. Did you forget to set up your virtualenv?"
    log_action "ERROR: .venv directory not found!"
    if [[ $AUTO -eq 1 ]]; then
        echo "Auto mode: missing venv, cannot continue. Skipping with success."
        auto_exit_success
    else
        exit 1
    fi
fi

echo "[6.1] Upgrading pip to latest version in venv..."
python -m pip install --upgrade pip

pip install -e .

echo "[7] Running test command..."
if ! gway test --on-failure abort; then
    echo "Error: gway test failed after upgrade."
    log_action "Upgrade failed at commit: $NEW_HASH"
    if [[ $AUTO -eq 1 ]]; then
        echo "Auto mode enabled: attempting revert to previous version."
        if restore_snapshot; then
            echo "Revert completed."
        else
            echo "Warning: revert failed or not possible, proceeding with last known code."
            log_action "WARNING: revert failed or not possible in auto mode."
        fi
        auto_exit_success
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
auto_exit_success
