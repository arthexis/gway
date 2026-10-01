def test_arthexis_bootstrap_promotes_certified_gway_to_system_runtime(sampler_path):
    script = sampler_path("bootstrap/arthexis.sh").read_text(encoding="utf-8")

    assert 'GWAY_SHA="${GWAY_BOOTSTRAP_SHA:-}"' in script
    assert '"gway_sha"' in script
    assert 'SYSTEM_GWAY_VENV="${GWAY_SYSTEM_VENV:-/opt/gway/venv}"' in script
    assert 'SYSTEM_GWAY_COMMAND="${GWAY_SYSTEM_COMMAND:-/usr/local/bin/gway}"' in script
    assert (
        'SYSTEM_GWAY_SOURCE="gway @ https://github.com/arthexis/gway/archive/'
        '$GWAY_SHA.tar.gz"'
        in script
    )
    assert 'run_root "$UV" pip install' in script
    assert '--python "$SYSTEM_GWAY_CANDIDATE/bin/python"' in script
    assert '"$SYSTEM_GWAY_SOURCE"' in script
    assert '--upgrade "$SYSTEM_GWAY_SOURCE"' not in script
    assert "pypi.org" not in script.lower()


def test_arthexis_bootstrap_replaces_system_runtime_transactionally(sampler_path):
    script = sampler_path("bootstrap/arthexis.sh").read_text(encoding="utf-8")

    assert 'SYSTEM_GWAY_CANDIDATE="${SYSTEM_GWAY_VENV}.candidate.$$"' in script
    assert 'SYSTEM_GWAY_BACKUP="${SYSTEM_GWAY_VENV}.previous.$$"' in script
    assert 'run_root "$UV" venv "$SYSTEM_GWAY_CANDIDATE" --python python3' in script
    assert 'CANDIDATE_GWAY_VERSION="$(run_root "$SYSTEM_GWAY_CANDIDATE/bin/gway" version)"' in script
    assert 'run_root mv "$SYSTEM_GWAY_VENV" "$SYSTEM_GWAY_BACKUP"' in script
    assert 'run_root mv "$SYSTEM_GWAY_CANDIDATE" "$SYSTEM_GWAY_VENV"' in script
    assert 'SYSTEM_GWAY_PROMOTED=1' in script
    assert 'run_root rm -rf "$SYSTEM_GWAY_BACKUP"' in script
    assert 'SYSTEM_GWAY_PROMOTED=0' in script


def test_arthexis_bootstrap_rolls_back_failed_system_promotion(sampler_path):
    script = sampler_path("bootstrap/arthexis.sh").read_text(encoding="utf-8")

    assert 'if test "$status" -ne 0 && test "$SYSTEM_GWAY_PROMOTED" = 1; then' in script
    assert 'run_root rm -rf "$SYSTEM_GWAY_VENV" || true' in script
    assert 'run_root mv "$SYSTEM_GWAY_BACKUP" "$SYSTEM_GWAY_VENV" || true' in script
    assert 'if test -n "$SYSTEM_GWAY_CANDIDATE"; then' in script
    assert 'run_root rm -rf "$SYSTEM_GWAY_CANDIDATE" || true' in script


def test_arthexis_bootstrap_installs_one_context_aware_system_wrapper(sampler_path):
    script = sampler_path("bootstrap/arthexis.sh").read_text(encoding="utf-8")

    assert '# GWAY_SYSTEM_BOOTSTRAP_WRAPPER=1' in script
    assert 'if test "\\$(id -u)" -eq 0; then' in script
    assert 'GWAY_CONFIG_HOME="\\${GWAY_CONFIG_HOME:-$SYSTEM_GWAY_CONFIG}"' in script
    assert 'GWAY_DATA_HOME="\\${GWAY_DATA_HOME:-$SYSTEM_GWAY_DATA}"' in script
    assert 'export GIT_TERMINAL_PROMPT=0' in script
    assert 'exec "$SYSTEM_GWAY_VENV/bin/gway" "\\$@"' in script


def test_arthexis_bootstrap_verifies_then_removes_temporary_uv_gway(sampler_path):
    script = sampler_path("bootstrap/arthexis.sh").read_text(encoding="utf-8")

    bootstrap_version = 'USER_GWAY_VERSION="$("$GWAY" version)"'
    candidate_version = 'CANDIDATE_GWAY_VERSION="$(run_root "$SYSTEM_GWAY_CANDIDATE/bin/gway" version)"'
    system_version = 'SYSTEM_GWAY_VERSION="$($SYSTEM_GWAY_COMMAND version)"'
    root_version = 'ROOT_GWAY_VERSION="$(run_root "$SYSTEM_GWAY_COMMAND" version)"'
    uninstall = '"$UV" tool uninstall gway'
    switch = 'GWAY="$SYSTEM_GWAY_COMMAND"'

    assert bootstrap_version in script
    assert candidate_version in script
    assert system_version in script
    assert root_version in script
    assert uninstall in script
    assert switch in script
    assert script.index(bootstrap_version) < script.index(candidate_version)
    assert script.index(candidate_version) < script.index(uninstall)
    assert script.index(system_version) < script.index(uninstall)
    assert script.index(root_version) < script.index(uninstall)
    assert script.index(uninstall) < script.index(switch)
    assert "bootstrap/candidate Gway version mismatch" in script
    assert "user/system Gway version mismatch after promotion" in script


def test_arthexis_bootstrap_cleans_wrapper_tempfile_on_failure(sampler_path):
    script = sampler_path("bootstrap/arthexis.sh").read_text(encoding="utf-8")

    assert 'SYSTEM_WRAPPER_TMP=""' in script
    assert 'if test -n "$SYSTEM_WRAPPER_TMP"; then' in script
    assert 'rm -f "$SYSTEM_WRAPPER_TMP"' in script
    assert script.index('if test -n "$SYSTEM_WRAPPER_TMP"; then') < script.index('trap cleanup EXIT HUP INT TERM')
