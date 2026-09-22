from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from gway.logs import LogRecord


def test_log_record_requires_timezone_aware_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        LogRecord(
            timestamp=datetime(2026, 9, 22, 12, 0),
            source="gway",
            message="hello",
        )


def test_log_record_is_immutable_and_copies_metadata():
    metadata = {"backend": "journal"}
    record = LogRecord(
        timestamp=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
        source="gway",
        message="hello",
        metadata=metadata,
    )

    metadata["backend"] = "changed"

    assert record.metadata["backend"] == "journal"
    with pytest.raises(TypeError):
        record.metadata["backend"] = "changed"
    with pytest.raises(FrozenInstanceError):
        record.message = "changed"
