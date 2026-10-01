import runpy


def test_satellite_renderer_enables_service_autostart(sampler_path):
    namespace = runpy.run_path(str(sampler_path("bootstrap/watchtower.py")))
    installer = namespace["installer"]

    assert installer("satellite")["installer_autostart"] == "1"
    assert installer("control")["installer_autostart"] == "0"


def test_autostart_bootstrap_starts_and_verifies_required_services(sampler_path):
    script = sampler_path("bootstrap/arthexis.sh").read_text(encoding="utf-8")

    assert 'if test "[installer_autostart|0]" = "1"; then' in script
    assert 'for service in web worker beat; do' in script
    assert '"$GWAY" service start --name "$service" -- arthexis "$service"' in script
    assert 'ARTHEXIS_BOOTSTRAP_START_SETTLE' in script
    assert (
        '"$GWAY" service status --name "$service" -- arthexis "$service" '
        "| grep -q '^Running: yes$'"
        in script
    )
    assert "required service '$service' did not remain running" in script


def test_autostart_verification_precedes_installation_complete(sampler_path):
    script = sampler_path("bootstrap/arthexis.sh").read_text(encoding="utf-8")

    verification = 'if test "[installer_autostart|0]" = "1"; then'
    complete = '"[installer_title] installation complete."'
    assert script.index(verification) < script.index(complete)
