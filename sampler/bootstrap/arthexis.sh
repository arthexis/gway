#!/bin/sh
set -eu

if test -n "${GWAY_BOOTSTRAP_GWAY:-}"; then
    GWAY="$GWAY_BOOTSTRAP_GWAY"
    test -x "$GWAY" || {
        echo "Arthexis bootstrap: GWAY_BOOTSTRAP_GWAY is not executable: $GWAY" >&2
        exit 1
    }
else
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
fi

# Install the Arthexis half of the same Watchtower-certified pair used by the
# Gway bootstrap. Do not resolve moving repository HEAD here.
ARTHEXIS_SOURCE="${ARTHEXIS_BOOTSTRAP_SOURCE:-arthexis/arthexis}"
ARTHEXIS_SHA="${ARTHEXIS_BOOTSTRAP_SHA:-}"

if test -z "$ARTHEXIS_SHA"; then
    CERTIFIED_MANIFEST_URL="https://raw.githubusercontent.com/arthexis/arthexis/watchtower-state/.watchtower/accepted.json"
    MANIFEST="$(mktemp)"
    trap 'rm -f "$MANIFEST"' EXIT
    curl -fsSL "$CERTIFIED_MANIFEST_URL" -o "$MANIFEST"
    ARTHEXIS_SHA="$(awk -F'"' '/"arthexis_sha"/ { print $4; exit }' "$MANIFEST")"
fi

if test "${#ARTHEXIS_SHA}" -ne 40; then
    echo "Arthexis bootstrap: no valid arthexis_sha was supplied or accepted" >&2
    exit 1
fi
case "$ARTHEXIS_SHA" in
    *[[!0-9a-f]]*)
        echo "Arthexis bootstrap: arthexis_sha is invalid" >&2
        exit 1
        ;;
esac

if test "$ARTHEXIS_SOURCE" = "arthexis/arthexis"; then
    "$GWAY" install "$ARTHEXIS_SOURCE" --ref "$ARTHEXIS_SHA"
else
    "$GWAY" install "$ARTHEXIS_SOURCE"
fi

ARTHEXIS_HOME="${ARTHEXIS_BOOTSTRAP_HOME:-$HOME/.local/opt/arthexis}"
ARTHEXIS_DATA_DIR="$ARTHEXIS_HOME/var"
mkdir -p "$ARTHEXIS_DATA_DIR"
ARTHEXIS_DATA_DIR="$ARTHEXIS_DATA_DIR" "$GWAY" arthexis migrate --no-interactive
ARTHEXIS_DATA_DIR="$ARTHEXIS_DATA_DIR" "$GWAY" arthexis seed

if test "${ARTHEXIS_BOOTSTRAP_VERIFY_ONLY:-0}" = "1"; then
    printf '%s\n' "Arthexis bootstrap verification complete."
    exit 0
fi

"$GWAY" service install -- arthexis web
"$GWAY" service install -- arthexis worker
"$GWAY" service install -- arthexis beat

"$GWAY" service restart -- arthexis web
"$GWAY" service restart -- arthexis worker
"$GWAY" service restart -- arthexis beat

printf '%s\n' "[installer_title] installation complete."
printf '%s\n' "[installer_description]"
