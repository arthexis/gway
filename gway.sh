#!/bin/bash
set -e

# Change to the directory where this script is located
cd "$(dirname "$0")"

# If .venv doesn't exist, create it and install gway in editable mode
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
  source .venv/bin/activate
  echo "Installing gway in editable mode..."
  pip install --upgrade pip
  pip install -e .

  # Install additional requirements if the file exists
  if [ -f "temp/requirements.txt" ]; then
    echo "Installing additional requirements from temp/requirements.txt..."
    pip install -r temp/requirements.txt
  fi

  deactivate
fi

# Activate the virtual environment
source .venv/bin/activate

# Run the Python module
python3 -m gway "$@"

# Deactivate the virtual environment
deactivate
