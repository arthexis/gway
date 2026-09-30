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

# Install the Arthexis half of the same Watchtower-certified pair used by the
# Gway bootstrap. Do not resolve moving repository HEAD here.
CERTIFIED_MANIFEST_URL="https://raw.githubusercontent.com/arthexis/arthexis/watchtower-state/.watchtower/accepted.json"
MANIFEST="$(mktemp)"
trap 'rm -f "$MANIFEST"' EXIT
curl -fsSL "$CERTIFIED_MANIFEST_URL" -o "$MANIFEST"

ARTHEXIS_SHA="$(awk -F'"' '/"arthexis_sha"/ { print $4; exit }' "$MANIFEST")"
if test "${#ARTHEXIS_SHA}" -ne 40; then
    echo "Arthexis bootstrap: accepted Watchtower manifest has no valid arthexis_sha" >&2
    exit 1
fi
case "$ARTHEXIS_SHA" in
    *[[!0-9a-f]]*)
        echo "Arthexis bootstrap: accepted Watchtower manifest has an invalid arthexis_sha" >&2
        exit 1
        ;;
esac

"$GWAY" install arthexis/arthexis --ref "$ARTHEXIS_SHA"
"$GWAY" arthexis migrate --noinput
"$GWAY" arthexis seed

"$GWAY" service install -- arthexis web
"$GWAY" service install -- arthexis worker
"$GWAY" service install -- arthexis beat

"$GWAY" service restart -- arthexis web
"$GWAY" service restart -- arthexis worker
"$GWAY" service restart -- arthexis beat

printf '%s\n' "[installer_title] installation complete."
printf '%s\n' "[installer_description]"
