#!/usr/bin/env bash
# Install or upgrade GWAY 1.x as a system/appliance command.
#
# Typical fresh-box usage:
#   curl -fsSL https://raw.githubusercontent.com/arthexis/gway/main/install.sh | sudo bash
#
# Existing /usr/local/bin/gway commands that are not this managed wrapper are
# archived before replacement so pre-1.x GWAY remains recoverable.

set -euo pipefail

INSTALL_ROOT="${GWAY_INSTALL_ROOT:-/opt/gway}"
VENV="${GWAY_VENV:-${INSTALL_ROOT}/venv}"
BIN_DIR="${GWAY_BIN_DIR:-/usr/local/bin}"
WRAPPER="${BIN_DIR}/gway"
LEGACY_WRAPPER="${BIN_DIR}/gway-legacy"
CONFIG_HOME="${GWAY_SYSTEM_CONFIG_HOME:-/etc/gway}"
DATA_HOME="${GWAY_SYSTEM_DATA_HOME:-/var/lib/gway}"
SOURCE_SPEC="${GWAY_SOURCE_SPEC:-git+https://github.com/arthexis/gway.git@main}"
PYTHON=""

usage() {
    cat <<'EOF'
GWAY system bootstrap installer

Usage:
  sudo ./install.sh
  ./install.sh --check

Modes:
  --check   Validate prerequisites and report what would be installed.
  -h        Show this help.

Environment overrides:
  GWAY_PYTHON              Python >=3.11 interpreter to use.
  GWAY_INSTALL_ROOT        Installation root (default: /opt/gway).
  GWAY_BIN_DIR             Wrapper directory (default: /usr/local/bin).
  GWAY_SYSTEM_CONFIG_HOME  System config directory (default: /etc/gway).
  GWAY_SYSTEM_DATA_HOME    System data directory (default: /var/lib/gway).
  GWAY_SOURCE_SPEC         pip source spec for GWAY.
EOF
}

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

require_root() {
    [[ "${EUID}" -eq 0 ]] || die "run this command as root (for example with sudo)"
}

python_is_supported() {
    "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
        >/dev/null 2>&1
}

find_python() {
    local candidate
    if [[ -n "${GWAY_PYTHON:-}" ]]; then
        command -v "${GWAY_PYTHON}" >/dev/null 2>&1 \
            || die "GWAY_PYTHON is not executable: ${GWAY_PYTHON}"
        python_is_supported "${GWAY_PYTHON}" \
            || die "GWAY_PYTHON must be Python 3.11 or newer"
        PYTHON="$(command -v "${GWAY_PYTHON}")"
        return
    fi

    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "${candidate}" >/dev/null 2>&1 \
            && python_is_supported "${candidate}"; then
            PYTHON="$(command -v "${candidate}")"
            return
        fi
    done

    die "Python 3.11 or newer is required; install it without replacing the OS python3"
}

ensure_git() {
    if command -v git >/dev/null 2>&1; then
        return
    fi
    if [[ -f /etc/debian_version ]] && command -v apt-get >/dev/null 2>&1; then
        apt-get update
        DEBIAN_FRONTEND=noninteractive apt-get install -y git ca-certificates
        return
    fi
    die "git is required to install ${SOURCE_SPEC}"
}

create_venv() {
    local py_version
    py_version="$(${PYTHON} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    install -d -o root -g root -m 755 "${INSTALL_ROOT}"

    if [[ -x "${VENV}/bin/python" ]] \
        && "${VENV}/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
            >/dev/null 2>&1; then
        return
    fi

    rm -rf "${VENV}"
    if "${PYTHON}" -m venv "${VENV}"; then
        return
    fi

    if [[ -f /etc/debian_version ]] && command -v apt-get >/dev/null 2>&1; then
        apt-get update
        DEBIAN_FRONTEND=noninteractive apt-get install -y "python${py_version}-venv"
        "${PYTHON}" -m venv "${VENV}"
        return
    fi
    die "could not create virtual environment with ${PYTHON}"
}

is_managed_wrapper() {
    [[ -f "$1" ]] && grep -q '^# GWAY_SYSTEM_BOOTSTRAP_WRAPPER=1$' "$1" 2>/dev/null
}

archive_existing_gway() {
    local archive suffix counter
    if [[ ! -e "${WRAPPER}" && ! -L "${WRAPPER}" ]]; then
        return 0
    fi
    if is_managed_wrapper "${WRAPPER}"; then
        return 0
    fi

    archive="${LEGACY_WRAPPER}"
    if [[ -e "${archive}" || -L "${archive}" ]]; then
        if cmp -s "${WRAPPER}" "${archive}" 2>/dev/null; then
            rm -f "${WRAPPER}"
            printf 'legacy GWAY already archived at %s\n' "${archive}"
            return
        fi
        suffix="$(date -u +%Y%m%dT%H%M%SZ)"
        archive="${LEGACY_WRAPPER}.${suffix}"
        counter=1
        while [[ -e "${archive}" || -L "${archive}" ]]; do
            archive="${LEGACY_WRAPPER}.${suffix}.${counter}"
            ((counter += 1))
        done
    fi

    mv "${WRAPPER}" "${archive}"
    printf 'archived existing GWAY command as %s\n' "${archive}"
}

install_wrapper() {
    install -d -o root -g root -m 755 "${BIN_DIR}"
    archive_existing_gway
    cat >"${WRAPPER}" <<EOF
#!/bin/sh
# GWAY_SYSTEM_BOOTSTRAP_WRAPPER=1
export GWAY_CONFIG_HOME="\${GWAY_CONFIG_HOME:-${CONFIG_HOME}}"
export GWAY_DATA_HOME="\${GWAY_DATA_HOME:-${DATA_HOME}}"
export GIT_TERMINAL_PROMPT=0
exec "${VENV}/bin/gway" "\$@"
EOF
    chmod 755 "${WRAPPER}"
}

check_configuration() {
    find_python
    command -v git >/dev/null 2>&1 \
        || die "git is required (the installer can add it on Debian-family systems when run as root)"
    printf 'Python:       %s (%s)\n' "${PYTHON}" "$(${PYTHON} --version 2>&1)"
    printf 'Install root: %s\n' "${INSTALL_ROOT}"
    printf 'Command:      %s\n' "${WRAPPER}"
    printf 'Config home:  %s\n' "${CONFIG_HOME}"
    printf 'Data home:    %s\n' "${DATA_HOME}"
    if [[ -e "${WRAPPER}" || -L "${WRAPPER}" ]]; then
        if is_managed_wrapper "${WRAPPER}"; then
            printf 'Existing GWAY: managed system wrapper (will upgrade in place)\n'
        else
            printf 'Existing GWAY: legacy/unmanaged command (will archive before replacement)\n'
        fi
    else
        printf 'Existing GWAY: none\n'
    fi
    printf 'system bootstrap configuration valid\n'
}

install_gway() {
    require_root
    find_python
    ensure_git
    create_venv

    export GIT_TERMINAL_PROMPT=0
    "${VENV}/bin/python" -m pip install --upgrade pip
    "${VENV}/bin/python" -m pip install --upgrade "${SOURCE_SPEC}"

    install -d -o root -g root -m 755 "${CONFIG_HOME}" "${DATA_HOME}"
    install_wrapper

    "${WRAPPER}" --version
    printf 'GWAY system installation ready\n'
}

main() {
    local mode="install"
    while (($#)); do
        case "$1" in
            --check)
                mode="check"
                ;;
            -h|--help)
                usage
                return 0
                ;;
            *)
                die "unknown argument '$1'"
                ;;
        esac
        shift
    done

    case "${mode}" in
        check)
            check_configuration
            ;;
        install)
            install_gway
            ;;
        *)
            die "internal error: unknown mode '${mode}'"
            ;;
    esac
}

if [[ -z "${BASH_SOURCE[0]:-}" || "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
