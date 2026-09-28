#!/bin/sh
# GWAY_BOOTSTRAP_V1
set -eu

if command -v uv >/dev/null 2>&1; then
    UV="$(command -v uv)"
else
    curl -LsSf https://astral.sh/uv/install.sh | sh
    if command -v uv >/dev/null 2>&1; then
        UV="$(command -v uv)"
    elif test -x "$HOME/.local/bin/uv"; then
        UV="$HOME/.local/bin/uv"
    else
        echo "gway bootstrap: uv installation did not produce an executable" >&2
        exit 1
    fi
fi

"$UV" tool install --upgrade gway

if command -v gway >/dev/null 2>&1; then
    GWAY="$(command -v gway)"
elif test -x "$HOME/.local/bin/gway"; then
    GWAY="$HOME/.local/bin/gway"
else
    echo "gway bootstrap: installation completed but gway is not executable" >&2
    exit 1
fi

"$GWAY" version
