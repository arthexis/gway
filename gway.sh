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
  echo "Installing gway in editable mode..."
  pip install --upgrade pip
  pip install -e .

  deactivate
fi

# Activate the virtual environment
source .venv/bin/activate

# Run the Python module
python3 -m gway "$@"

# Deactivate the virtual environment
deactivate
