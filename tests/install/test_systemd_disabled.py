from gway import Gateway


def test_service_install_systemd_can_remain_disabled(
    tmp_path,
    monkeypatch,
    fake_systemd,
    install_environment,
):
    monkeypatch.chdir(tmp_path)
    units, calls = fake_systemd

    records = Gateway()(
        "service install --backend systemd --no-enable --name simulator sous chef"
    )

    assert (units / "gway-simulator.service").is_file()
    assert records[0].service == "simulator"
    assert (("disable", "gway-simulator.service"), False, True) in calls
    assert (("enable", "gway-simulator.service"), False, True) not in calls
