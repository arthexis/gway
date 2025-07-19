#!/usr/bin/env bash
# file: upgrade.sh

set -e

ACTION_LOG=".upgrade_action.log"

usage() {
    echo "Usage: $0 [--force] [--no-test]"
    echo "  --force     Reinstall and test even if no update is detected."
    echo "  --no-test   Skip running tests after upgrade."
    exit 0
}

FORCE=0
RUN_TESTS=1
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        --no-test) RUN_TESTS=0 ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $arg"; usage ;;
    esac
done

log_action() {
    echo "$(date -Iseconds) | $1" >> "$ACTION_LOG"
}

echo "[1] Checking current commit hash..."
OLD_HASH=$(git rev-parse HEAD)

echo "[2] Fetching latest commits from Git..."
if ! git fetch --all --prune; then
    echo "Warning: git fetch failed, continuing with existing code"
    log_action "git fetch failed: offline?"
fi

echo "[3] Resetting to origin/main and cleaning up..."
git reset --hard origin/main
git clean -fd

NEW_HASH=$(git rev-parse HEAD)

echo "[4] Ensuring scripts are executable..."
chmod +x *.sh

if [[ "$OLD_HASH" == "$NEW_HASH" && $FORCE -eq 0 ]]; then
    echo "No updates detected. Skipping reinstall (use --force to override)."
    echo "Upgrade script completed."
    log_action "No updates: $NEW_HASH"
    exit 0
fi

echo "[5] Activating venv and reinstalling package in editable mode..."
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "Error: .venv directory not found. Did you forget to set up your virtualenv?"
    log_action "ERROR: .venv directory not found!"
    exit 1
fi

echo "[5.1] Upgrading pip to latest version in venv..."
python -m pip install --upgrade pip || log_action "pip upgrade failed"

if ! pip install -e .; then
    echo "Warning: package installation failed, continuing"
    log_action "pip install failed"
fi

if [ $RUN_TESTS -eq 1 ]; then
    echo "[6] Running test command..."
    if ! gway test --on-failure abort; then
        echo "Error: gway test failed after upgrade."
        log_action "Upgrade failed at commit: $NEW_HASH"
        exit 1
    fi
    echo "Upgrade and test completed successfully."
    log_action "Upgrade success: $NEW_HASH"
else
    echo "[6] Skipping tests (--no-test)"
    echo "Upgrade completed successfully."
    log_action "Upgrade success (no test): $NEW_HASH"
fi

exit 0
