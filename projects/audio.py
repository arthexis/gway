# file: projects/audio.py

from __future__ import annotations

import os
import threading
import time
import wave
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
from gway import gw


def record(
    *,
    duration: float = 5.0,
    samplerate: int = 44_100,
    channels: int = 1,
    format: str = "wav",
    file: Optional[str] = None,
):
    """Record audio from the default input device.

    Args:
        duration: Seconds to record. Defaults to 5 seconds.
        samplerate: Sampling frequency. Defaults to 44100 Hz.
        channels: Number of channels. Defaults to 1 (mono).
        format: Audio format. Currently only ``"wav"`` is supported.
        file: Target filename. If ``None``, a name like
            ``"recording_<timestamp>.wav"`` is saved to the ``work``
            directory.

    Returns:
        Absolute path to the recorded audio file.
    """
    if format.lower() != "wav":
        raise ValueError("Only 'wav' format is supported")

    if file is None:
        work_dir = gw.resource("work", dir=True)
        path = work_dir / f"recording_{int(time.time())}.{format}"
    else:
        path = Path(file)
        if not path.is_absolute():
            path = Path.cwd() / path
    path = path.resolve()
    gw.info(f"Recording audio to {path}")

    frames = int(duration * samplerate)
    data = sd.rec(frames, samplerate=samplerate, channels=channels)
    sd.wait()
    scaled = np.int16(data * 32767)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(scaled.tobytes())
    gw.info(f"Saved recording to {path}")
    return str(path)


def playback(audio: str, *, loop: bool = False):
    """Play an audio file.

    Args:
        audio: Path to a ``.wav`` file. It can be the result returned by
            :func:`record` to enable chaining.
        loop: When ``True`` the audio is played continuously in the
            background using Gateway's async thread management.
    """
    audio = os.path.abspath(audio)
    if not os.path.isfile(audio):
        raise FileNotFoundError(audio)

    def _play_once():
        with wave.open(audio, "rb") as wf:
            samplerate = wf.getframerate()
            channels = wf.getnchannels()
            frames = wf.readframes(wf.getnframes())
        data = np.frombuffer(frames, dtype=np.int16)
        data = data.reshape(-1, channels)
        sd.play(data, samplerate)
        sd.wait()

    if loop:
        def _loop():
            while True:
                _play_once()
        thread = threading.Thread(target=_loop, daemon=True)
        thread.start()
        gw._async_threads.append(thread)
        gw.info(f"Looping playback of {audio}")
        return f"Looping playback of {audio}"
    else:
        _play_once()
        gw.info(f"Played {audio}")
        return f"Played {audio}"
