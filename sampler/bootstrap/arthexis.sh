#!/bin/sh
set -eu

curl -fsSL "https://[domain]/gway" | sh

if command -v gway >/dev/null 2>&1; then
    GWAY="$(command -v gway)"
elif test -x "$HOME/.local/bin/gway"; then
    GWAY="$HOME/.local/bin/gway"
else
    echo "GWAY was installed but could not be located in this shell." >&2
    exit 1
fi

"$GWAY" install arthexis/arthexis
"$GWAY" arthexis migrate --noinput
"$GWAY" arthexis seed

printf '%s\n' "[installer_title] installation complete."
printf '%s\n' "[installer_description]"
