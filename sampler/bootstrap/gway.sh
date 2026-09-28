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

# Make uv-managed tools available to this bootstrap process immediately and
# persist the tool directory for future shells. A piped child shell cannot
# mutate the PATH of the already-running parent shell.
export PATH="$HOME/.local/bin:$PATH"
"$UV" tool update-shell >/dev/null 2>&1 || true

if command -v gway >/dev/null 2>&1; then
    GWAY="$(command -v gway)"
elif test -x "$HOME/.local/bin/gway"; then
    GWAY="$HOME/.local/bin/gway"
else
    echo "gway bootstrap: installation completed but gway is not executable" >&2
    exit 1
fi

"$GWAY" --help >/dev/null
echo "gway bootstrap: installation verified"
