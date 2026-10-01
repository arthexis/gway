import subprocess


def test_arthexis_bootstrap_is_posix_shell_syntax_valid(sampler_path):
    script = sampler_path("bootstrap/arthexis.sh")

    result = subprocess.run(
        ["sh", "-n", str(script)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_appliance_bootstrap_converges_on_one_certified_gway_runtime(sampler_path):
    script = sampler_path("bootstrap/arthexis.sh").read_text(encoding="utf-8")

    # The appliance runtime comes from the exact Watchtower-certified SHA,
    # not from the latest package that happens to exist on PyPI.
    assert 'SYSTEM_GWAY_SOURCE="gway @ https://github.com/arthexis/gway/archive/' in script
    assert '$GWAY_SHA.tar.gz"' in script
    assert 'SYSTEM_GWAY_VENV="${GWAY_SYSTEM_VENV:-/opt/gway/venv}"' in script
    assert 'SYSTEM_GWAY_COMMAND="${GWAY_SYSTEM_COMMAND:-/usr/local/bin/gway}"' in script
    assert "pypi.org" not in script.lower()

    # Both normal and privileged execution are certified against that runtime
    # before the temporary user bootstrap tool is removed.
    assert 'SYSTEM_GWAY_VERSION="$($SYSTEM_GWAY_COMMAND version)"' in script
    assert 'ROOT_GWAY_VERSION="$(run_root "$SYSTEM_GWAY_COMMAND" version)"' in script
    assert '"$UV" tool uninstall gway' in script
    assert 'if test -e "$TOOL_BIN/gway"; then' in script
    assert 'GWAY="$SYSTEM_GWAY_COMMAND"' in script


def test_appliance_bootstrap_preserves_current_service_cli_contract(sampler_path):
    script = sampler_path("bootstrap/arthexis.sh").read_text(encoding="utf-8")

    # This is the command that exposed the split-brain 1.0.1/1.1.x install.
    # Keep the installed appliance contract tied to the current plural
    # `statuses` surface rather than the obsolete singular-only CLI.
    assert '"gway service statuses --project arthexis"' in script
    assert '"$GWAY" service install --name web' in script
    assert '"$GWAY" service restart --name web' in script


def test_appliance_bootstrap_reports_success_only_after_service_health(sampler_path):
    script = sampler_path("bootstrap/arthexis.sh").read_text(encoding="utf-8")

    health = 'systemctl --user is-active --quiet "$unit"'
    failure = "service verification failed; installation is incomplete"
    success = '"[installer_title] installation complete."'

    assert health in script
    assert failure in script
    assert success in script
    assert script.index(health) < script.index(failure) < script.index(success)
