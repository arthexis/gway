from gway import gw

def _write_sample_log(path):
    sample = "\n".join(
        [
            "[UnityCrossThreadLogger]2024-02-14 22:03:11.123: Client -> Match: SubmitDeck {",
            '  "matchId": "abc-123",',
            '  "eventId": "evt-001"',
            "}",
            "[UnityCrossThreadLogger]2024-02-14 22:03:12.555: Match <- Server: GameState {",
            '  "matchId": "abc-123",',
            '  "turnNumber": 4',
            "}",
            "[UnityCrossThreadLogger]2024-02-14 22:03:13.000: Info: GREMessageType_JoinMatchArena",
        ]
    )
    path.write_text(sample, encoding="utf-8")


def test_scan_logs_parses_events(tmp_path):
    log_path = tmp_path / "Player.log"
    _write_sample_log(log_path)

    result = gw.mtg.scan_logs(source=log_path)

    assert result["path"] == str(log_path)

    entries = result["entries"]
    assert len(entries) == 3

    first, second, third = entries

    assert first["direction"] == "outbound"
    assert first["actor"] == "Client"
    assert first["target"] == "Match"
    assert first["event"] == "SubmitDeck"
    assert first["payload"]["matchId"] == "abc-123"
    assert first["payload"]["eventId"] == "evt-001"

    assert second["direction"] == "inbound"
    assert second["event"] == "GameState"
    assert second["payload"]["turnNumber"] == 4

    assert third["message"] == "Info: GREMessageType_JoinMatchArena"

    stats = result["stats"]
    assert stats["total_entries"] == 3
    assert stats["json_entries"] == 2
    assert stats["text_entries"] == 1
    assert stats["events"] == {"SubmitDeck": 1, "GameState": 1}


def test_scan_logs_limit_returns_latest_entries(tmp_path):
    log_path = tmp_path / "Player.log"
    _write_sample_log(log_path)

    limited = gw.mtg.scan_logs(source=log_path, limit=1)

    assert len(limited["entries"]) == 1
    assert limited["entries"][0]["message"] == "Info: GREMessageType_JoinMatchArena"
    assert limited["stats"]["total_entries"] == 1
    assert limited["stats"]["json_entries"] == 0
