#!/usr/bin/env bash
set -euo pipefail

mode="${1:---check}"

case "$mode" in
  --fix)
    python -m ruff check --fix src tests
    python -m ruff format src tests
    ;;
  --check)
    python -m ruff check src tests
    python -m ruff format --check src tests
    ;;
  *)
    echo "usage: scripts/quality.sh [--check|--fix]" >&2
    exit 2
    ;;
esac
