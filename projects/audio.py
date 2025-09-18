# file: projects/audio.py

from __future__ import annotations

import os
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

import numpy as np
import sounddevice as sd
from gway import gw


@dataclass
class AudioStream:
    """In-memory audio capture ready to be streamed or played back."""

    data: np.ndarray
    samplerate: int
    channels: int
    path: Path

    def iter_chunks(self, *, frames: int = 1024) -> Iterator[np.ndarray]:
        """Yield successive chunks of the captured audio.

        Args:
            frames: Number of frames to emit per chunk.

        Yields:
            ``numpy.ndarray`` slices containing ``frames`` worth of audio data.
        """

        if frames <= 0:
            raise ValueError("frames must be a positive integer")

        total_frames = self.data.shape[0]
        for start in range(0, total_frames, frames):
            yield self.data[start : start + frames]


def record(
    *,
    duration: float = 5.0,
    samplerate: int = 44_100,
    channels: int = 1,
    format: str = "wav",
    file: Optional[str] = None,
    immediate: bool = False,
    sample: Optional[float] = None,
    stream: bool = False,
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
        immediate: Start recording immediately without waiting for
            user input.
        sample: Maximum seconds to capture. When provided the effective
            recording duration is ``min(duration, sample)``.
        stream: When ``True`` return an :class:`AudioStream` with the
            captured data for real-time streaming instead of a file path.

    Returns:
        Absolute path to the recorded audio file, or an :class:`AudioStream`
        instance when ``stream`` is ``True``.
    """
    if format.lower() != "wav":
        raise ValueError("Only 'wav' format is supported")

    if sample is not None:
        if sample <= 0:
            raise ValueError("sample must be a positive duration")
        effective_duration = min(duration, sample)
    else:
        effective_duration = duration

    if effective_duration <= 0:
        raise ValueError("Recording duration must be positive")

    if file is None:
        work_dir = gw.resource("work", dir=True)
        path = work_dir / f"recording_{int(time.time())}.{format}"
    else:
        path = Path(file)
        if not path.is_absolute():
            path = Path.cwd() / path
    path = path.resolve()
    gw.info(f"Recording audio to {path}")
    if not immediate:
        gw.info("Press Enter to start recording")
        input()

    frames = int(round(effective_duration * samplerate))
    if frames <= 0:
        raise ValueError("Recording duration too short for the given sample rate")
    data = sd.rec(frames, samplerate=samplerate, channels=channels)
    sd.wait()
    float_data = np.array(data, copy=True)
    scaled = np.int16(np.clip(float_data, -1, 1) * 32767)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(scaled.tobytes())
    gw.info(f"Saved recording to {path}")
    if stream:
        return AudioStream(
            data=float_data,
            samplerate=samplerate,
            channels=channels,
            path=path,
        )
    return str(path)


def playback(*, audio: str | AudioStream, loop: bool = False):
    """Play an audio file.

    Args:
        audio: Path to a ``.wav`` file or an :class:`AudioStream` instance.
            It can be the result returned by :func:`record` to enable
            chaining.
        loop: When ``True`` the audio is played continuously in the
            background using Gateway's async thread management.
    """
    if isinstance(audio, AudioStream):
        samplerate = audio.samplerate

        def _play_once():
            sd.play(audio.data, samplerate)
            sd.wait()
    else:
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
        target = audio.path if isinstance(audio, AudioStream) else audio
        target_str = str(target)
        gw.info(f"Looping playback of {target_str}")
        return f"Looping playback of {target_str}"
    else:
        _play_once()
        target = audio.path if isinstance(audio, AudioStream) else audio
        target_str = str(target)
        gw.info(f"Played {target_str}")
        return f"Played {target_str}"
