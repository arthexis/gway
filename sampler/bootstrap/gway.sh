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

# Install the exact Gway revision certified by Watchtower instead of depending
# on PyPI publication. Use GitHub's immutable source archive so a fresh machine
# does not need a system Git executable just to bootstrap Gway.
CERTIFIED_MANIFEST_URL="https://raw.githubusercontent.com/arthexis/arthexis/watchtower-state/.watchtower/accepted.json"
MANIFEST="$(mktemp)"
trap 'rm -f "$MANIFEST"' EXIT
curl -fsSL "$CERTIFIED_MANIFEST_URL" -o "$MANIFEST"

GWAY_SHA="$(awk -F'"' '/"gway_sha"/ { print $4; exit }' "$MANIFEST")"
if test "${#GWAY_SHA}" -ne 40; then
    echo "gway bootstrap: accepted Watchtower manifest has no valid gway_sha" >&2
    exit 1
fi
case "$GWAY_SHA" in
    *[[!0-9a-f]]*)
        echo "gway bootstrap: accepted Watchtower manifest has an invalid gway_sha" >&2
        exit 1
        ;;
esac

GWAY_SOURCE="gway @ https://github.com/arthexis/gway/archive/$GWAY_SHA.tar.gz"
"$UV" tool install --force --upgrade "$GWAY_SOURCE"

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
echo "gway bootstrap: installation verified ($GWAY_SHA)"
