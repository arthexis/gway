#!/bin/bash
set -e

echo "[1] Checking current commit hash..."
OLD_HASH=$(git rev-parse HEAD)

echo "[2] Fetching latest commits from Git..."
git fetch --all --prune

echo "[3] Resetting to origin/main and cleaning up..."
git reset --hard origin/main
git clean -fd

NEW_HASH=$(git rev-parse HEAD)

if [ "$OLD_HASH" == "$NEW_HASH" ]; then
    echo "No updates detected. Skipping reinstall."
else
    echo "[4] Reinstalling package in editable mode..."
    source .venv/bin/activate
    pip install -e .

    echo "[5] Setting executable permissions for scripts..."
    chmod +x gway.sh upgrade.sh

    echo "[6] Running test command..."
    gway hello-world
fi

echo "Upgrade script completed."
