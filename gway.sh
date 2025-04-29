#!/bin/bash
set -e

# Change to the directory where this script is located
cd "$(dirname "$0")"

# Activate the virtual environment
source .venv/bin/activate

# Run the Python module
python3 -m gway "$@"

# Deactivate the virtual environment
deactivate
