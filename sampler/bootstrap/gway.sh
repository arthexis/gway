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

# Persist uv's configured tool executable directory for future shells before
# exposing it to this child process. A piped shell cannot mutate its parent.
TOOL_BIN="$("$UV" tool dir --bin)"
if ! "$UV" tool update-shell >/dev/null 2>&1; then
    echo "gway bootstrap: warning: could not persist tool PATH for future shells" >&2
    echo "gway bootstrap: for this shell run: export PATH=\"$TOOL_BIN:\$PATH\"" >&2
fi
export PATH="$TOOL_BIN:$PATH"

if command -v gway >/dev/null 2>&1; then
    GWAY="$(command -v gway)"
elif test -x "$TOOL_BIN/gway"; then
    GWAY="$TOOL_BIN/gway"
else
    echo "gway bootstrap: installation completed but gway is not executable" >&2
    exit 1
fi

"$GWAY" --help >/dev/null
echo "gway bootstrap: installation verified"
