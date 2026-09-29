#!/bin/sh
set -eu

curl -fsSL "https://[domain]/gway" | sh

if command -v uv >/dev/null 2>&1; then
    UV="$(command -v uv)"
elif test -x "$HOME/.local/bin/uv"; then
    UV="$HOME/.local/bin/uv"
else
    echo "GWAY bootstrap completed but uv could not be located in this shell." >&2
    exit 1
fi

TOOL_BIN="$("$UV" tool dir --bin)"
if test -x "$TOOL_BIN/gway"; then
    GWAY="$TOOL_BIN/gway"
else
    echo "GWAY was installed but could not be located in uv's tool directory." >&2
    exit 1
fi

"$GWAY" install arthexis/arthexis
"$GWAY" arthexis migrate --noinput
"$GWAY" arthexis seed

printf '%s\n' "[installer_title] installation complete."
printf '%s\n' "[installer_description]"
