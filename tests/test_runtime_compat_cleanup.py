from __future__ import annotations

import gway.runtime as runtime
import gway.runtime_base as runtime_base
from gway.upgrade import UpgradeError


def test_upgrade_error_is_only_exposed_from_upgrade_module() -> None:
    assert UpgradeError.__module__ == "gway.upgrade"
    assert not hasattr(runtime, "UpgradeError")
    assert not hasattr(runtime_base, "UpgradeError")
