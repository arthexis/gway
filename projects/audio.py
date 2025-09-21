# file: projects/audio.py

from __future__ import annotations

import os
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, TYPE_CHECKING

import numpy as np
import speech_recognition as sr
from gway import gw


try:  # pragma: no cover - import guard is runtime dependent
    import sounddevice as _sounddevice
except Exception as exc:  # pragma: no cover - exercised via tests with patched import
    sd = None
    _SOUNDDEVICE_IMPORT_ERROR: Exception | None = exc
else:  # pragma: no cover - exercised when sounddevice is available
    sd = _sounddevice
    _SOUNDDEVICE_IMPORT_ERROR = None

if TYPE_CHECKING:  # pragma: no cover - mypy-only guard
    import sounddevice as sd  # noqa: F401  (re-export for type checkers)


def _ensure_sounddevice(action: str) -> None:
    """Raise a helpful error when PortAudio/sounddevice support is missing."""

    if sd is not None:
        return

    message = (
        "Audio {action} requires the 'sounddevice' package with a working "
        "PortAudio backend. Install the PortAudio shared library (for example "
        "'apt-get install libportaudio2' on Debian/Ubuntu) and reinstall "
        "sounddevice, or provide a pre-recorded file via the 'source' "
        "parameter instead."
    ).format(action=action)
    if _SOUNDDEVICE_IMPORT_ERROR is not None:
        message += f" (original error: {_SOUNDDEVICE_IMPORT_ERROR})"
    raise RuntimeError(message)


def recording_available() -> bool:
    """Return ``True`` when live recording is supported on this system."""

    return sd is not None


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

    _ensure_sounddevice("recording")

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
    _ensure_sounddevice("playback")

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


def transcribe(
    *,
    source: str | os.PathLike[str] | AudioStream | None = None,
    duration: float = 5.0,
    samplerate: int = 44_100,
    channels: int = 1,
    language: str = "en-US",
    engine: str = "auto",
    immediate: bool = True,
):
    """Transcribe speech from an audio source.

    Args:
        source: Path to an audio file or an :class:`AudioStream`. When ``None``
            a fresh recording is captured using :func:`record`.
        duration: Seconds to capture when ``source`` is ``None``. Defaults to
            5 seconds.
        samplerate: Recording sample rate used when capturing audio.
        channels: Number of channels recorded when capturing audio.
        language: Language hint passed to the recognition backend.
        engine: Recognition backend to use (``"sphinx"``, ``"google"`` or
            ``"auto"``). ``"auto"`` tries ``"sphinx"`` first and then falls
            back to ``"google"``.
        immediate: When recording a new sample, start immediately without
            waiting for user confirmation.

    Returns:
        Dictionary summarizing the transcription attempt. The transcript is
        stored under ``"audio_transcript"`` and ``"transcript"`` keys for easy
        chaining in recipes.
    """

    if source is None:
        if duration <= 0:
            raise ValueError("duration must be a positive number of seconds")
        if samplerate <= 0:
            raise ValueError("samplerate must be a positive integer")
        if channels <= 0:
            raise ValueError("channels must be a positive integer")

        gw.info("No audio source supplied; capturing a fresh sample")
        recorded = gw.audio.record(
            duration=duration,
            samplerate=samplerate,
            channels=channels,
            immediate=immediate,
        )
        if isinstance(recorded, AudioStream):
            audio_path = recorded.path
        else:
            audio_path = Path(recorded)
    elif isinstance(source, AudioStream):
        audio_path = source.path
    else:
        audio_path = Path(source)

    audio_path = audio_path.expanduser().resolve()
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    recognizer = sr.Recognizer()
    with sr.AudioFile(str(audio_path)) as audio_file:
        audio_data = recognizer.record(audio_file)

    requested_engine = engine.lower()
    if requested_engine not in {"sphinx", "google", "auto"}:
        raise ValueError(
            "engine must be one of 'sphinx', 'google' or 'auto'"
        )

    engines_to_try: tuple[str, ...]
    if requested_engine == "auto":
        engines_to_try = ("sphinx", "google")
    else:
        engines_to_try = (requested_engine,)

    transcript = ""
    error: str | None = None
    used_engine: str | None = None

    for current_engine in engines_to_try:
        try:
            if current_engine == "google":
                transcript = recognizer.recognize_google(audio_data, language=language)
            else:
                transcript = recognizer.recognize_sphinx(audio_data, language=language)
            used_engine = current_engine
            error = None
            break
        except sr.UnknownValueError:
            transcript = ""
            used_engine = current_engine
            error = "unknown-value"
            break
        except sr.RequestError as exc:
            transcript = ""
            used_engine = current_engine
            error = f"request-error: {exc}"
            if requested_engine == "auto":
                continue
            break

    if used_engine is None:
        used_engine = engines_to_try[-1]

    if transcript:
        preview = transcript if len(transcript) <= 60 else transcript[:57] + "..."
        gw.info(f"Transcribed audio via {used_engine}: {preview}")
    elif error:
        gw.warning(f"Transcription using {used_engine} failed: {error}")
    else:
        gw.info(f"No speech detected using {used_engine}")

    result: dict[str, str] = {
        "audio_transcript": transcript,
        "transcript": transcript,
        "audio_source": str(audio_path),
        "audio_transcription_engine": used_engine,
        "audio_transcription_language": language,
        "audio_transcription_status": "ok" if transcript else "error" if error else "empty",
        "audio_transcription_requested_engine": requested_engine,
    }
    if error:
        result["audio_transcription_error"] = error

    return result
