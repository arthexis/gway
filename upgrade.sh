#!/bin/bash
set -e

echo "[1] Stashing local changes (if any)..."
git stash save "Auto-stash before upgrade" || true

echo "[2] Pulling latest code from Git..."
GIT_OUTPUT=$(git pull)

if [[ "$GIT_OUTPUT" == "Already up to date." ]]; then
    echo "No updates pulled. Restoring stash (if any) and exiting..."
    git stash pop || true
    exit 0
fi

echo "[3] Reinstalling package in editable mode..."
source .venv/bin/activate
pip install -e .

echo "[4] Setting executable permissions for scripts..."
chmod +x gway.sh upgrade.sh

echo "[5] Running test command..."
gway hello-world

echo "Upgrade completed successfully."
