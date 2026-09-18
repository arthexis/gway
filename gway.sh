#!/usr/bin/env bash
set -euo pipefail

REQ_FILE="requirements.txt"
REQ_HASH_FILE="requirements.md5"
REQUIREMENTS_UPDATED=false

compute_requirements_hash() {
  python3 - "$1" <<'PY'
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
print(hashlib.md5(path.read_bytes()).hexdigest())
PY
}

sync_requirements() {
  local force="${1-}"
  REQUIREMENTS_UPDATED=false

  if [ ! -f "$REQ_FILE" ]; then
    if [ -f "$REQ_HASH_FILE" ]; then
      rm -f "$REQ_HASH_FILE"
    fi
    return 0
  fi

  local current_hash
  current_hash="$(compute_requirements_hash "$REQ_FILE")"

  local stored_hash=""
  if [ -f "$REQ_HASH_FILE" ]; then
    stored_hash="$(<"$REQ_HASH_FILE")"
  fi

  local reinstall="false"
  if [ "$force" = "--force" ]; then
    reinstall="true"
  elif [ -z "$stored_hash" ] || [ "$current_hash" != "$stored_hash" ]; then
    reinstall="true"
  fi

  if [ "$reinstall" = "true" ]; then
    echo "Installing requirements..."
    if pip install -r "$REQ_FILE"; then
      printf '%s\n' "$current_hash" > "$REQ_HASH_FILE"
      REQUIREMENTS_UPDATED=true
    else
      echo "ERROR: Failed to install requirements." >&2
      return 1
    fi
  fi

  return 0
}

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
  if ! sync_requirements "--force"; then
    deactivate
    exit 1
  fi
  pip install -e .

  deactivate
fi

# Activate the virtual environment
source .venv/bin/activate

if ! sync_requirements; then
  deactivate
  exit 1
fi

# Run the Python module; if a dependency is missing, install requirements and retry
if ! python3 -m gway "$@" 2> >(tee /tmp/gway_err.log >&2); then
  if grep -q "ModuleNotFoundError" /tmp/gway_err.log; then
    echo "Missing dependency detected. Checking requirements..."
    if sync_requirements; then
      if [ "$REQUIREMENTS_UPDATED" = true ]; then
        pip install -e .
        python3 -m gway "$@"
      else
        echo "requirements.txt is unchanged; skipping reinstall." >&2
        deactivate
        exit 1
      fi
    else
      deactivate
      exit 1
    fi
  else
    deactivate
    exit 1
  fi
fi

# Deactivate the virtual environment
deactivate
