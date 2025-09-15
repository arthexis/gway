import subprocess
from pathlib import Path


def test_cli_logs_to_history(tmp_path):
    history = tmp_path / "work" / "history.txt"

    result = subprocess.run(["gway", "-h"], cwd=tmp_path)

    assert result.returncode == 0
    assert history.exists()
    assert history.read_text(encoding="utf-8").strip() == "-h"

