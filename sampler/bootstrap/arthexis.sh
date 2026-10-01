#!/bin/sh
set -eu

BOOTSTRAP_YES="${ARTHEXIS_BOOTSTRAP_YES:-[installer_yes|0]}"
while test "$#" -gt 0; do
    case "$1" in
        --yes|-y)
            BOOTSTRAP_YES=1
            ;;
        *)
            echo "Arthexis bootstrap: unknown option: $1" >&2
            echo "Supported option: --yes" >&2
            exit 2
            ;;
    esac
    shift
done

ARTHEXIS_HOME="${ARTHEXIS_BOOTSTRAP_HOME:-$HOME/.local/opt/arthexis}"
ARTHEXIS_DATA_DIR="$ARTHEXIS_HOME/var"
ARTHEXIS_DATABASE_PATH="$ARTHEXIS_DATA_DIR/db.sqlite3"
MANIFEST=""
RUNTIME_HOLD=""
DATABASE_BACKUP=""

restore_runtime() {
    if test -n "$RUNTIME_HOLD" && test -d "$RUNTIME_HOLD/var"; then
        mkdir -p "$ARTHEXIS_HOME"
        if test -e "$ARTHEXIS_DATA_DIR"; then
            echo "Arthexis bootstrap: cannot restore runtime data because $ARTHEXIS_DATA_DIR already exists" >&2
            return 1
        fi
        mv "$RUNTIME_HOLD/var" "$ARTHEXIS_DATA_DIR"
        rmdir "$RUNTIME_HOLD" 2>/dev/null || true
        RUNTIME_HOLD=""
    fi
}

cleanup() {
    status=$?
    trap - EXIT HUP INT TERM
    restore_runtime || true
    if test -n "$MANIFEST"; then
        rm -f "$MANIFEST"
    fi
    exit "$status"
}
trap cleanup EXIT HUP INT TERM

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

DATABASE_EXISTS=0
if test -f "$ARTHEXIS_DATABASE_PATH"; then
    DATABASE_EXISTS=1
fi

if test "$DATABASE_EXISTS" = 1 && test "${ARTHEXIS_BOOTSTRAP_VERIFY_ONLY:-0}" != 1; then
    if test "$BOOTSTRAP_YES" != 1; then
        if ! exec 3<>/dev/tty 2>/dev/null; then
            echo "Arthexis bootstrap: an existing database requires upgrade approval." >&2
            echo "Re-run with 'sh -s -- --yes' or use '?yes=1' on the installer URL." >&2
            exit 2
        fi
        printf '\nExisting Arthexis database: %s\n' "$ARTHEXIS_DATABASE_PATH" >&3
        printf '%s\n' "The certified source update may require database migrations." >&3
        printf '%s\n' "A SQLite-consistent backup will be created before the update." >&3
        printf '%s' "Continue with the database update? [[y/N]] " >&3
        answer=""
        IFS= read -r answer <&3 || true
        exec 3>&-
        case "$answer" in
            y|Y|yes|YES|Yes)
                ;;
            *)
                echo "Arthexis bootstrap: database update cancelled."
                exit 0
                ;;
        esac
    fi

    BACKUP_DIR="$ARTHEXIS_DATA_DIR/backups"
    mkdir -p "$BACKUP_DIR"
    BACKUP_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
    DATABASE_BACKUP="$BACKUP_DIR/db-$BACKUP_STAMP.sqlite3"
    python3 - "$ARTHEXIS_DATABASE_PATH" "$DATABASE_BACKUP" <<'PY'
import sqlite3
import sys

_, source_path, backup_path = sys.argv
source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
target = sqlite3.connect(backup_path)
try:
    source.backup(target)
finally:
    target.close()
    source.close()
PY
    printf 'Database backup: %s\n' "$DATABASE_BACKUP"
fi

# Stop known Arthexis services before moving durable runtime state out of the
# managed product tree. Missing services are expected on first install.
for service in web worker beat; do
    "$GWAY" service stop --name "$service" -- arthexis "$service" >/dev/null 2>&1 || true
done
# Retire the pre-role service identity if this node was installed by an older bootstrap.
if command -v systemctl >/dev/null 2>&1; then
    systemctl --user stop arthexis-arthexis-arthexis.service >/dev/null 2>&1 || true
fi

# Runtime data is deliberately protected outside the managed source tree while
# Gway reconciles source. This keeps real source drift checks strict while
# ensuring product replacement can never discard the database or its backups.
if test -d "$ARTHEXIS_DATA_DIR"; then
    RUNTIME_HOLD="$(mktemp -d "${TMPDIR:-/tmp}/arthexis-runtime.XXXXXX")"
    mv "$ARTHEXIS_DATA_DIR" "$RUNTIME_HOLD/var"
fi

if test "$ARTHEXIS_SOURCE" = "arthexis/arthexis"; then
    "$GWAY" install "$ARTHEXIS_SOURCE" --ref "$ARTHEXIS_SHA"
else
    "$GWAY" install "$ARTHEXIS_SOURCE"
fi

if test -n "$RUNTIME_HOLD"; then
    if test -e "$ARTHEXIS_DATA_DIR"; then
        echo "Arthexis bootstrap: candidate source unexpectedly created reserved runtime path $ARTHEXIS_DATA_DIR" >&2
        exit 1
    fi
    restore_runtime
fi

mkdir -p "$ARTHEXIS_DATA_DIR"
ARTHEXIS_DATA_DIR="$ARTHEXIS_DATA_DIR" "$GWAY" arthexis migrate --no-interactive
ARTHEXIS_DATA_DIR="$ARTHEXIS_DATA_DIR" "$GWAY" arthexis seed

if test "${ARTHEXIS_BOOTSTRAP_VERIFY_ONLY:-0}" = "1"; then
    printf '%s\n' "Arthexis bootstrap verification complete."
    exit 0
fi

"$GWAY" service install --name web --environment "ARTHEXIS_DATA_DIR=$ARTHEXIS_DATA_DIR" -- arthexis web
"$GWAY" service install --name worker --environment "ARTHEXIS_DATA_DIR=$ARTHEXIS_DATA_DIR" -- arthexis worker
"$GWAY" service install --name beat --environment "ARTHEXIS_DATA_DIR=$ARTHEXIS_DATA_DIR" -- arthexis beat

"$GWAY" service restart --name web -- arthexis web
"$GWAY" service restart --name worker -- arthexis worker
"$GWAY" service restart --name beat -- arthexis beat

printf '\n%s\n' "[installer_title] installation complete."
printf '  Arthexis project: %s\n' "$ARTHEXIS_HOME"
printf '  Data directory:   %s\n' "$ARTHEXIS_DATA_DIR"
printf '  Revision:         %s\n' "$ARTHEXIS_SHA"
printf '  Services:         web, worker, beat\n'
if test -n "$DATABASE_BACKUP"; then
    printf '  Database backup:  %s\n' "$DATABASE_BACKUP"
fi
printf '\nUseful command:\n'
printf '  %s\n' "gway service statuses --project arthexis"
