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
SYSTEM_WRAPPER_TMP=""
SYSTEM_GWAY_CANDIDATE=""
SYSTEM_GWAY_BACKUP=""
SYSTEM_GWAY_PROMOTED=0
GWAY_BOOTSTRAPPED=0
GWAY_TEMP_TOOL=0
UV=""

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

cleanup_temp_gway() {
    if test "$GWAY_TEMP_TOOL" != 1; then
        return
    fi

    cleanup_uv="$UV"
    if test -z "$cleanup_uv"; then
        if command -v uv >/dev/null 2>&1; then
            cleanup_uv="$(command -v uv)"
        elif test -x "$HOME/.local/bin/uv"; then
            cleanup_uv="$HOME/.local/bin/uv"
        fi
    fi

    if test -n "$cleanup_uv"; then
        "$cleanup_uv" tool uninstall gway >/dev/null 2>&1 || true
    fi
    GWAY_TEMP_TOOL=0
}

cleanup() {
    status=$?
    trap - EXIT HUP INT TERM
    restore_runtime || true
    if test -n "$MANIFEST"; then
        rm -f "$MANIFEST"
    fi
    if test -n "$SYSTEM_WRAPPER_TMP"; then
        rm -f "$SYSTEM_WRAPPER_TMP"
    fi
    if test -n "$SYSTEM_GWAY_CANDIDATE"; then
        run_root rm -rf "$SYSTEM_GWAY_CANDIDATE" || true
    fi
    if test "$status" -ne 0 && test "$SYSTEM_GWAY_PROMOTED" = 1; then
        run_root rm -rf "$SYSTEM_GWAY_VENV" || true
        if test -n "$SYSTEM_GWAY_BACKUP" && run_root test -e "$SYSTEM_GWAY_BACKUP"; then
            run_root mv "$SYSTEM_GWAY_BACKUP" "$SYSTEM_GWAY_VENV" || true
        fi
    fi
    cleanup_temp_gway
    exit "$status"
}
trap cleanup EXIT HUP INT TERM

run_root() {
    if test "$(id -u)" -eq 0; then
        "$@"
        return
    fi
    if ! command -v sudo >/dev/null 2>&1; then
        echo "Arthexis bootstrap: sudo is required to provision the system Gway runtime." >&2
        exit 1
    fi
    sudo "$@"
}

if test -n "${GWAY_BOOTSTRAP_GWAY:-}"; then
    GWAY="$GWAY_BOOTSTRAP_GWAY"
    test -x "$GWAY" || {
        echo "Arthexis bootstrap: GWAY_BOOTSTRAP_GWAY is not executable: $GWAY" >&2
        exit 1
    }
else
    curl -fsSL "https://[domain]/gway" | sh
    GWAY_BOOTSTRAPPED=1
    GWAY_TEMP_TOOL=1

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

ARTHEXIS_SOURCE="${ARTHEXIS_BOOTSTRAP_SOURCE:-arthexis/arthexis}"
ARTHEXIS_SHA="${ARTHEXIS_BOOTSTRAP_SHA:-}"
GWAY_SHA="${GWAY_BOOTSTRAP_SHA:-}"

if test -z "$ARTHEXIS_SHA" || { test "$GWAY_BOOTSTRAPPED" = 1 && test -z "$GWAY_SHA"; }; then
    CERTIFIED_MANIFEST_URL="https://raw.githubusercontent.com/arthexis/arthexis/watchtower-state/.watchtower/accepted.json"
    MANIFEST="$(mktemp)"
    curl -fsSL "$CERTIFIED_MANIFEST_URL" -o "$MANIFEST"
    if test -z "$ARTHEXIS_SHA"; then
        ARTHEXIS_SHA="$(awk -F'"' '/"arthexis_sha"/ { print $4; exit }' "$MANIFEST")"
    fi
    if test "$GWAY_BOOTSTRAPPED" = 1 && test -z "$GWAY_SHA"; then
        GWAY_SHA="$(awk -F'"' '/"gway_sha"/ { print $4; exit }' "$MANIFEST")"
    fi
fi

if test "${#ARTHEXIS_SHA}" -ne 40; then
    echo "Arthexis bootstrap: no valid arthexis_sha was supplied or accepted" >&2
    exit 1
fi
case "$ARTHEXIS_SHA" in
    *[!0-9a-f]*)
        echo "Arthexis bootstrap: arthexis_sha is invalid" >&2
        exit 1
        ;;
esac

# Satellite and Control bootstrap use a temporary per-user uv tool only long
# enough to obtain Gway on a fresh machine. Build the accepted Watchtower
# revision in a clean candidate venv, validate it, then atomically replace the
# appliance runtime. A failed promotion restores the previous runtime.
if test "$GWAY_BOOTSTRAPPED" = 1; then
    if test "${#GWAY_SHA}" -ne 40; then
        echo "Arthexis bootstrap: accepted Watchtower manifest has no valid gway_sha" >&2
        exit 1
    fi
    case "$GWAY_SHA" in
        *[!0-9a-f]*)
            echo "Arthexis bootstrap: gway_sha is invalid" >&2
            exit 1
            ;;
    esac

    SYSTEM_GWAY_VENV="${GWAY_SYSTEM_VENV:-/opt/gway/venv}"
    SYSTEM_GWAY_COMMAND="${GWAY_SYSTEM_COMMAND:-/usr/local/bin/gway}"
    SYSTEM_GWAY_CONFIG="${GWAY_SYSTEM_CONFIG_HOME:-/etc/gway}"
    SYSTEM_GWAY_DATA="${GWAY_SYSTEM_DATA_HOME:-/var/lib/gway}"
    SYSTEM_GWAY_SOURCE="gway @ https://github.com/arthexis/gway/archive/$GWAY_SHA.tar.gz"
    SYSTEM_GWAY_CANDIDATE="${SYSTEM_GWAY_VENV}.candidate.$$"
    SYSTEM_GWAY_BACKUP="${SYSTEM_GWAY_VENV}.previous.$$"

    run_root mkdir -p "$(dirname "$SYSTEM_GWAY_VENV")"
    run_root rm -rf "$SYSTEM_GWAY_CANDIDATE" "$SYSTEM_GWAY_BACKUP"
    run_root "$UV" venv "$SYSTEM_GWAY_CANDIDATE" --python python3
    run_root "$UV" pip install \
        --python "$SYSTEM_GWAY_CANDIDATE/bin/python" \
        "$SYSTEM_GWAY_SOURCE"

    USER_GWAY_VERSION="$("$GWAY" version)"
    CANDIDATE_GWAY_VERSION="$(run_root "$SYSTEM_GWAY_CANDIDATE/bin/gway" version)"
    if test "$USER_GWAY_VERSION" != "$CANDIDATE_GWAY_VERSION"; then
        echo "Arthexis bootstrap: bootstrap/candidate Gway version mismatch" >&2
        echo "  bootstrap: $USER_GWAY_VERSION" >&2
        echo "  candidate: $CANDIDATE_GWAY_VERSION" >&2
        exit 1
    fi

    if run_root test -e "$SYSTEM_GWAY_VENV"; then
        run_root mv "$SYSTEM_GWAY_VENV" "$SYSTEM_GWAY_BACKUP"
    fi
    run_root mv "$SYSTEM_GWAY_CANDIDATE" "$SYSTEM_GWAY_VENV"
    SYSTEM_GWAY_CANDIDATE=""
    SYSTEM_GWAY_PROMOTED=1

    run_root mkdir -p "$SYSTEM_GWAY_CONFIG" "$SYSTEM_GWAY_DATA" "$(dirname "$SYSTEM_GWAY_COMMAND")"

    SYSTEM_WRAPPER_TMP="$(mktemp)"
    cat >"$SYSTEM_WRAPPER_TMP" <<EOF
#!/bin/sh
# GWAY_SYSTEM_BOOTSTRAP_WRAPPER=1
if test "\$(id -u)" -eq 0; then
    export GWAY_CONFIG_HOME="\${GWAY_CONFIG_HOME:-$SYSTEM_GWAY_CONFIG}"
    export GWAY_DATA_HOME="\${GWAY_DATA_HOME:-$SYSTEM_GWAY_DATA}"
fi
export GIT_TERMINAL_PROMPT=0
exec "$SYSTEM_GWAY_VENV/bin/gway" "\$@"
EOF
    run_root install -m 755 "$SYSTEM_WRAPPER_TMP" "$SYSTEM_GWAY_COMMAND"
    rm -f "$SYSTEM_WRAPPER_TMP"
    SYSTEM_WRAPPER_TMP=""

    SYSTEM_GWAY_VERSION="$($SYSTEM_GWAY_COMMAND version)"
    ROOT_GWAY_VERSION="$(run_root "$SYSTEM_GWAY_COMMAND" version)"
    if test "$USER_GWAY_VERSION" != "$SYSTEM_GWAY_VERSION" || test "$USER_GWAY_VERSION" != "$ROOT_GWAY_VERSION"; then
        echo "Arthexis bootstrap: user/system Gway version mismatch after promotion" >&2
        echo "  bootstrap: $USER_GWAY_VERSION" >&2
        echo "  user:      $SYSTEM_GWAY_VERSION" >&2
        echo "  root:      $ROOT_GWAY_VERSION" >&2
        exit 1
    fi

    if run_root test -e "$SYSTEM_GWAY_BACKUP"; then
        run_root rm -rf "$SYSTEM_GWAY_BACKUP"
    fi
    SYSTEM_GWAY_BACKUP=""
    SYSTEM_GWAY_PROMOTED=0

    "$UV" tool uninstall gway
    GWAY_TEMP_TOOL=0
    if test -e "$TOOL_BIN/gway"; then
        echo "Arthexis bootstrap: temporary user Gway entrypoint survived cleanup: $TOOL_BIN/gway" >&2
        exit 1
    fi
    GWAY="$SYSTEM_GWAY_COMMAND"
    printf 'Gway appliance runtime: %s (%s)\n' "$SYSTEM_GWAY_COMMAND" "$SYSTEM_GWAY_VERSION"
fi

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
        printf '%s' "Continue with the database update? [y/N] " >&3
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

# Stop the stable unit identities directly before replacing source. This avoids
# depending on the old launchable definition still being resolvable during an upgrade.
if command -v systemctl >/dev/null 2>&1; then
    for service in web worker beat; do
        systemctl --user stop "arthexis-$service.service" >/dev/null 2>&1 || true
    done
    systemctl --user stop arthexis-arthexis-arthexis.service >/dev/null 2>&1 || true
else
    for service in web worker beat; do
        "$GWAY" service stop --name "$service" -- arthexis "$service" >/dev/null 2>&1 || true
    done
fi

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

ARTHEXIS_PYTHON="$ARTHEXIS_HOME/.venv/bin/python"
ARTHEXIS_CELERY="$ARTHEXIS_HOME/.venv/bin/celery"
test -x "$ARTHEXIS_PYTHON" || {
    echo "Arthexis bootstrap: missing Python runtime: $ARTHEXIS_PYTHON" >&2
    exit 1
}
"$ARTHEXIS_PYTHON" -c 'from arthexis.server import main' || {
    echo "Arthexis bootstrap: server runtime is not importable through $ARTHEXIS_PYTHON" >&2
    exit 1
}
test -x "$ARTHEXIS_CELERY" || {
    echo "Arthexis bootstrap: missing runtime entrypoint: $ARTHEXIS_CELERY" >&2
    exit 1
}
ARTHEXIS_WEB_RUN='from arthexis.server import main; import sys; main(host="127.0.0.1", port=int(sys.argv[1]), data_dir=sys.argv[2])'

if test "${ARTHEXIS_BOOTSTRAP_VERIFY_ONLY:-0}" = "1"; then
    ARTHEXIS_WEB_PORT="${ARTHEXIS_BOOTSTRAP_WEB_PORT:-0}"
else
    ARTHEXIS_WEB_PORT="${ARTHEXIS_BOOTSTRAP_WEB_PORT:-8888}"
fi

(
    cd "$ARTHEXIS_HOME"
    "$GWAY" service install --name web --environment "ARTHEXIS_DATA_DIR=$ARTHEXIS_DATA_DIR" -- "$ARTHEXIS_PYTHON" -c "$ARTHEXIS_WEB_RUN" "$ARTHEXIS_WEB_PORT" "$ARTHEXIS_DATA_DIR"
    "$GWAY" service install --name worker --environment "ARTHEXIS_DATA_DIR=$ARTHEXIS_DATA_DIR" -- "$ARTHEXIS_CELERY" -A arthexis.celery:app worker --loglevel INFO
    "$GWAY" service install --name beat --environment "ARTHEXIS_DATA_DIR=$ARTHEXIS_DATA_DIR" -- "$ARTHEXIS_CELERY" -A arthexis.celery:app beat --loglevel INFO

    "$GWAY" service restart --name web -- "$ARTHEXIS_PYTHON" -c "$ARTHEXIS_WEB_RUN" "$ARTHEXIS_WEB_PORT" "$ARTHEXIS_DATA_DIR"
    "$GWAY" service restart --name worker -- "$ARTHEXIS_CELERY" -A arthexis.celery:app worker --loglevel INFO
    "$GWAY" service restart --name beat -- "$ARTHEXIS_CELERY" -A arthexis.celery:app beat --loglevel INFO
)

SERVICE_SETTLE_SECONDS="${ARTHEXIS_BOOTSTRAP_SERVICE_SETTLE_SECONDS:-2}"
sleep "$SERVICE_SETTLE_SECONDS"

service_health_failed=0
if command -v systemctl >/dev/null 2>&1; then
    for service in web worker beat; do
        unit="arthexis-$service.service"
        if ! systemctl --user is-active --quiet "$unit"; then
            service_health_failed=1
            printf '\nArthexis bootstrap: service failed after restart: %s\n' "$service" >&2
            systemctl --user status "$unit" --no-pager --full >&2 || true
            if command -v journalctl >/dev/null 2>&1; then
                journalctl --user -u "$unit" -n 80 --no-pager >&2 || true
            fi
        fi
    done
else
    echo "Arthexis bootstrap: systemctl is required to verify installed services." >&2
    service_health_failed=1
fi

if test "$service_health_failed" != 0; then
    echo "Arthexis bootstrap: service verification failed; installation is incomplete." >&2
    exit 1
fi

if test "${ARTHEXIS_BOOTSTRAP_VERIFY_ONLY:-0}" = "1"; then
    for service in web worker beat; do
        systemctl --user stop "arthexis-$service.service" >/dev/null 2>&1 || true
    done
    printf '%s\n' "Arthexis bootstrap verification complete."
    exit 0
fi

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