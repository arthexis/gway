#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

export GWAY_BIN_DIR="${TMP_DIR}/bin"
export GWAY_INSTALL_ROOT="${TMP_DIR}/opt/gway"
export GWAY_SYSTEM_CONFIG_HOME="${TMP_DIR}/etc/gway"
export GWAY_SYSTEM_DATA_HOME="${TMP_DIR}/var/lib/gway"

# shellcheck source=../install.sh
source "${ROOT_DIR}/install.sh"
mkdir -p "${BIN_DIR}"

# First unmanaged/legacy command is preserved at the canonical archive path.
printf '#!/bin/sh\necho legacy-one\n' >"${WRAPPER}"
chmod 755 "${WRAPPER}"
archive_existing_gway
[[ ! -e "${WRAPPER}" ]]
[[ -x "${LEGACY_WRAPPER}" ]]
grep -q 'legacy-one' "${LEGACY_WRAPPER}"

# A managed wrapper is recognized and never archived on a rerun.
printf '#!/bin/sh\n# GWAY_SYSTEM_BOOTSTRAP_WRAPPER=1\necho managed\n' >"${WRAPPER}"
chmod 755 "${WRAPPER}"
archive_existing_gway
[[ -x "${WRAPPER}" ]]
grep -q 'managed' "${WRAPPER}"

# A different later legacy command never overwrites the first archive.
printf '#!/bin/sh\necho legacy-two\n' >"${WRAPPER}"
chmod 755 "${WRAPPER}"
archive_existing_gway
[[ ! -e "${WRAPPER}" ]]
grep -q 'legacy-one' "${LEGACY_WRAPPER}"
mapfile -t backups < <(compgen -G "${LEGACY_WRAPPER}.*")
[[ "${#backups[@]}" -eq 1 ]]
grep -q 'legacy-two' "${backups[0]}"

printf 'system installer legacy archival tests passed\n'
