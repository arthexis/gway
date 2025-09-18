#!/usr/bin/env bash
# file: upgrade.sh

set -e

ACTION_LOG=".upgrade_action.log"

REQUIREMENTS_FILE="requirements.txt"
REQUIREMENTS_HASH_FILE="requirements.md5"

compute_requirements_hash() {
    python - <<PY
import hashlib
from pathlib import Path
import sys

path = Path("$REQUIREMENTS_FILE")
if not path.is_file():
    sys.exit(1)

print(hashlib.md5(path.read_bytes()).hexdigest())
PY
}

usage() {
    echo "Usage: $0 [--force] [--latest] [--test] [--no-test]"
    echo "  --force     Reinstall even if no update is detected."
    echo "  --latest    Always reinstall, skipping the PyPI version check."
    echo "  --test      Run the full test suite after upgrading."
    echo "  --no-test   Skip all tests (including the smoke test)."
    exit 0
}

FORCE=0
ALWAYS_LATEST=0
REQUEST_FULL_TEST=0
REQUEST_SKIP_TEST=0
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        --latest) ALWAYS_LATEST=1 ;;
        --test) REQUEST_FULL_TEST=1 ;;
        --no-test) REQUEST_SKIP_TEST=1 ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $arg"; usage ;;
    esac
done

if [[ $REQUEST_FULL_TEST -eq 1 && $REQUEST_SKIP_TEST -eq 1 ]]; then
    echo "Error: --test and --no-test cannot be used together."
    exit 1
fi

TEST_MODE="smoke"
if [[ $REQUEST_FULL_TEST -eq 1 ]]; then
    TEST_MODE="full"
elif [[ $REQUEST_SKIP_TEST -eq 1 ]]; then
    TEST_MODE="skip"
fi

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

if [[ "$OLD_HASH" == "$NEW_HASH" && $FORCE -eq 0 && $ALWAYS_LATEST -eq 0 ]]; then
    echo "No updates detected. Skipping reinstall (use --force or --latest to override)."
    echo "Upgrade script completed."
    log_action "No updates: $NEW_HASH"
    exit 0
fi

echo "[5] Activating virtual environment..."
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "Error: .venv directory not found. Did you forget to set up your virtualenv?"
    log_action "ERROR: .venv directory not found!"
    exit 1
fi

if [[ $ALWAYS_LATEST -eq 0 && $FORCE -eq 0 ]]; then
    echo "[5.1] Checking installed gway version..."
    set +e
    CURRENT_VERSION=$(python - <<'PY'
import sys
try:
    from importlib import metadata
except ImportError:  # pragma: no cover - fallback for older Python
    import importlib_metadata as metadata  # type: ignore

try:
    print(metadata.version("gway"))
except metadata.PackageNotFoundError:  # type: ignore[attr-defined]
    pass
except Exception as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    sys.exit(1)
PY
    )
    VERSION_STATUS=$?
    set -e
    CURRENT_VERSION=$(echo "$CURRENT_VERSION" | tr -d '\r\n')
    if [[ $VERSION_STATUS -ne 0 ]]; then
        echo "Warning: failed to determine installed gway version. Continuing."
        log_action "Version check failed: installed"
        CURRENT_VERSION=""
    elif [[ -n "$CURRENT_VERSION" ]]; then
        echo "Current version: $CURRENT_VERSION"
    else
        echo "Installed version not found; proceeding with upgrade."
    fi

    echo "[5.2] Checking latest gway version on PyPI..."
    set +e
    PYPI_VERSION=$(python - <<'PY'
import json
import sys
import urllib.error
import urllib.request

URL = "https://pypi.org/pypi/gway/json"

try:
    with urllib.request.urlopen(URL, timeout=10) as resp:
        data = json.load(resp)
    print(data["info"]["version"])
except Exception as exc:  # pragma: no cover - network errors
    print(f"ERROR: {exc}", file=sys.stderr)
    sys.exit(1)
PY
    )
    PYPI_STATUS=$?
    set -e
    PYPI_VERSION=$(echo "$PYPI_VERSION" | tr -d '\r\n')
    if [[ $PYPI_STATUS -ne 0 || -z "$PYPI_VERSION" ]]; then
        echo "Warning: failed to fetch PyPI version. Continuing with upgrade."
        log_action "Version check failed: PyPI"
    else
        echo "PyPI version: $PYPI_VERSION"
        if [[ -n "$CURRENT_VERSION" && "$CURRENT_VERSION" == "$PYPI_VERSION" ]]; then
            echo "Installed version matches PyPI. Skipping upgrade (use --latest to override)."
            log_action "No new PyPI version: $CURRENT_VERSION"
            exit 0
        fi
    fi
fi

echo "[5.3] Upgrading pip to latest version in venv..."
python -m pip install --upgrade pip || log_action "pip upgrade failed"

echo "[5.4] Installing Python requirements..."
set +e
REQUIREMENTS_HASH=$(compute_requirements_hash 2>/dev/null)
HASH_STATUS=$?
set -e
REQUIREMENTS_HASH=$(echo "$REQUIREMENTS_HASH" | tr -d '\r\n')
if [[ $HASH_STATUS -ne 0 ]]; then
    REQUIREMENTS_HASH=""
fi

STORED_REQUIREMENTS_HASH=""
if [[ -f "$REQUIREMENTS_HASH_FILE" ]]; then
    STORED_REQUIREMENTS_HASH=$(tr -d '\r\n' < "$REQUIREMENTS_HASH_FILE")
fi

if [[ -n "$REQUIREMENTS_HASH" && "$REQUIREMENTS_HASH" == "$STORED_REQUIREMENTS_HASH" && $FORCE -eq 0 && $ALWAYS_LATEST -eq 0 ]]; then
    echo "Requirements unchanged (MD5). Skipping pip install (use --force or --latest to override)."
else
    if ! pip install -r "$REQUIREMENTS_FILE"; then
        echo "Warning: requirements installation failed, continuing"
        log_action "requirements install failed"
    else
        if [[ -z "$REQUIREMENTS_HASH" ]]; then
            set +e
            REQUIREMENTS_HASH=$(compute_requirements_hash 2>/dev/null)
            set -e
            REQUIREMENTS_HASH=$(echo "$REQUIREMENTS_HASH" | tr -d '\r\n')
        fi
        if [[ -n "$REQUIREMENTS_HASH" ]]; then
            printf '%s\n' "$REQUIREMENTS_HASH" > "$REQUIREMENTS_HASH_FILE"
        fi
    fi
fi

echo "[5.5] Installing gway in editable mode..."
if ! pip install -e .; then
    echo "Warning: package installation failed, continuing"
    log_action "pip install failed"
fi

case "$TEST_MODE" in
    full)
        echo "[6] Running full test suite..."
        if ! gway test --on-failure abort; then
            echo "Error: gway test failed after upgrade."
            log_action "Upgrade failed at commit: $NEW_HASH"
            exit 1
        fi
        echo "Upgrade and full test suite completed successfully."
        log_action "Upgrade success (full test): $NEW_HASH"
        ;;
    smoke)
        echo "[6] Running smoke tests..."
        if ! gway test --filter smoke --on-failure abort; then
            echo "Error: gway smoke tests failed after upgrade."
            log_action "Upgrade failed at commit: $NEW_HASH"
            exit 1
        fi
        echo "Upgrade and smoke test completed successfully."
        log_action "Upgrade success (smoke): $NEW_HASH"
        ;;
    skip)
        echo "[6] Skipping tests (--no-test)"
        echo "Upgrade completed successfully."
        log_action "Upgrade success (no test): $NEW_HASH"
        ;;
    *)
        echo "Unknown test mode: $TEST_MODE"
        exit 1
        ;;
esac

exit 0
