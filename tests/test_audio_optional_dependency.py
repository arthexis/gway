# file: tests/test_audio_optional_dependency.py

from __future__ import annotations

import builtins
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def _load_audio_without_sounddevice():
    audio_path = Path(__file__).resolve().parents[1] / "projects" / "audio.py"
    spec = importlib.util.spec_from_file_location("audio_missing_sounddevice", audio_path)
    module = importlib.util.module_from_spec(spec)

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "sounddevice":
            raise OSError("PortAudio library not found")
        return real_import(name, globals, locals, fromlist, level)

    with patch.dict(sys.modules, {spec.name: module}):
        with patch.object(builtins, "__import__", side_effect=fake_import):
            spec.loader.exec_module(module)
    return module


def test_audio_module_gracefully_handles_missing_sounddevice(tmp_path):
    audio = _load_audio_without_sounddevice()

    assert not audio.recording_available()

    target = tmp_path / "sample.wav"
    with pytest.raises(RuntimeError) as excinfo:
        audio.record(duration=1, immediate=True, file=target)

    message = str(excinfo.value)
    assert "sounddevice" in message
    assert "PortAudio" in message

