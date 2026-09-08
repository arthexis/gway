#!/usr/bin/env bash
set -euo pipefail

mode="${1:---check}"
shift || true
paths=("${@:-.}")

case "$mode" in
  --check)
    python -m ruff check "${paths[@]}"
    python -m ruff format --check "${paths[@]}"
    ;;
  --fix)
    python -m ruff check --fix "${paths[@]}"
    python -m ruff format "${paths[@]}"
    ;;
  *)
    echo "usage: .ci/quality.sh [--check|--fix] [paths ...]" >&2
    exit 2
    ;;
esac
