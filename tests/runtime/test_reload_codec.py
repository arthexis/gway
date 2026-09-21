from pathlib import Path

import pytest

from gway.install.model import Installation
from gway.reload import ReloadCheckpoint


def test_reload_checkpoint_roundtrips_managed_installation_record(tmp_path):
    installation = Installation(
        name="gway",
        source="file:///tmp/gway.git",
        requested_ref="upgrade-b",
        resolved_revision="abc123",
        fingerprint="sha256:deadbeef",
        install_path=tmp_path / "projects" / "gway",
        scope="user",
        installed_at="2026-09-21T00:00:00+00:00",
    )
    checkpoint = ReloadCheckpoint.create(
        result=installation,
        result_history=(installation,),
        result_subjects={"project": installation},
    )

    restored = ReloadCheckpoint.from_dict(checkpoint.as_dict())

    assert restored.result == installation
    assert restored.result.install_path == Path(installation.install_path)
    assert restored.result_history == (installation,)
    assert restored.result_subjects == {"project": installation}


def test_reload_checkpoint_still_rejects_arbitrary_python_objects():
    class Unsupported:
        pass

    with pytest.raises(TypeError, match="unsupported reload value Unsupported"):
        ReloadCheckpoint.create(result=Unsupported())
