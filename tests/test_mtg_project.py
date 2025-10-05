import pytest

from gway import gw


def test_scan_logs_is_deprecated():
    with pytest.raises(RuntimeError, match="deprecated"):
        gw.mtg.scan_logs()


def test_candidate_log_paths_is_deprecated():
    with pytest.raises(RuntimeError, match="deprecated"):
        gw.mtg.candidate_log_paths()
