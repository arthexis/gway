#!/usr/bin/env bash
set -euo pipefail

# Resolve the real directory of this script, even if it’s symlinked
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
cd "$SCRIPT_DIR"

# If .venv doesn't exist, create it and install gway in editable mode
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
  source .venv/bin/activate
  echo "Installing dependencies..."
  pip install --upgrade pip
  pip install -r requirements.txt
  pip install -e .

  deactivate
fi

# Activate the virtual environment
source .venv/bin/activate

# Run the Python module; if a dependency is missing, install requirements and retry
if ! python3 -m gway "$@" 2> >(tee /tmp/gway_err.log >&2); then
  if grep -q "ModuleNotFoundError" /tmp/gway_err.log; then
    echo "Missing dependency detected. Installing requirements..."
    pip install -r requirements.txt
    pip install -e .
    python3 -m gway "$@"
  else
    exit 1
  fi
fi

# Deactivate the virtual environment
deactivate
