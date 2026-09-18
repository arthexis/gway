# projects/mic.py
"""Simple microphone recording utility."""

from __future__ import annotations

import os
import wave
from datetime import datetime
from typing import Optional, Union

import numpy as np
from gway import gw


def record(
    duration: float = 5.0,
    *,
    device: Optional[Union[int, str]] = None,
    location: Optional[str] = None,
    samplerate: int = 44100,
    channels: int = 1,
) -> str | None:
    """Record audio from the microphone and save it to a WAV file.

    Parameters
    ----------
    duration:
        Length of the recording in seconds.
    device:
        Optional device name or index to use for recording.
    location:
        Directory where the recording will be stored. Defaults to
        ``gw.resource('work', 'mic', 'records')``.
    samplerate:
        Sample rate in Hz (defaults to 44100).
    channels:
        Number of audio channels (defaults to 1).

    Returns
    -------
    str | None
        Path to the saved WAV file or ``None`` if recording failed.
    """
    if location is None:
        base = gw.resource("work", "mic", "records")
    else:
        base = gw.resource(location)
    os.makedirs(base, exist_ok=True)

    start = datetime.now()
    start_stamp = start.strftime("%Y%m%d_%H%M%S")
    filename = f"{start_stamp}_{int(duration)}s.wav"
    filepath = os.path.join(base, filename)

    gw.info(f"Recording {duration}s to {filepath}")
    try:
        import sounddevice as sd
        recording = sd.rec(
            int(duration * samplerate),
            samplerate=samplerate,
            channels=channels,
            dtype="int16",
            device=device,
        )
        sd.wait()

        with wave.open(filepath, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)  # int16
            wf.setframerate(samplerate)
            wf.writeframes(recording.tobytes())

        return filepath
    except Exception as e:  # pragma: no cover - real recording can fail
        gw.error(f"Recording failed: {e}")
        return None

