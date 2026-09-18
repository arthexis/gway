# file: projects/transcriptor.py

from __future__ import annotations

import time
from typing import Iterable, Mapping

import speech_recognition as sr

from gway import gw


_DEFAULT_RESERVED_KEYS: set[str] = {
    "client",
    "server",
    "project_path",
    "projects",
    "section",
    "language",
    "engine",
    "pause",
    "phrase",
    "rest",
    "timeout",
    "energy",
    "ambient",
    "dynamic",
    "once",
    "default",
    "unknown",
    "reserved",
    "categories",
    "category",
}


def _coerce_float(value, *, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return False
    return text not in {"0", "false", "off", "no", "disable", "disabled"}


def _split_descriptors(values: Iterable[str]) -> list[str]:
    descriptors: list[str] = []
    for raw in values:
        if raw is None:
            continue
        text = str(raw).strip().lower()
        if not text:
            continue
        for token in text.replace(",", " ").split():
            token = token.strip()
            if token:
                descriptors.append(token)
    return descriptors


def configure(
    *,
    default: str = "uncategorized",
    unknown: str | None = None,
    reserved: str = "",
    **overrides,
) -> dict[str, object]:
    """Collect category descriptors from the CLI context."""

    sys_namespace = getattr(gw, "sys", {}) or {}
    cli_context = sys_namespace.get("cli_context")
    if not isinstance(cli_context, Mapping):
        cli_context = {}

    reserved_keys = set(_DEFAULT_RESERVED_KEYS)
    if reserved:
        reserved_keys.update(part.strip() for part in reserved.replace(",", " ").split() if part.strip())

    category_sources: dict[str, Iterable[str]] = {}
    for key, value in cli_context.items():
        if key in reserved_keys or key.startswith("SYS"):
            continue
        if key.startswith("transcriptor_"):
            continue
        if key in overrides:
            continue
        category_sources[key] = [value]

    for key, value in overrides.items():
        if key.startswith("transcriptor_"):
            continue
        category_sources[key] = [value]

    categories: dict[str, list[str]] = {}
    for name, values in category_sources.items():
        descriptors = _split_descriptors(values)
        if descriptors:
            categories[str(name)] = descriptors

    fallback_label = unknown or default
    payload = {
        "transcriptor_categories": categories,
        "transcriptor_category_default": default,
        "transcriptor_category_unknown": fallback_label,
        "transcriptor_category_names": sorted(categories),
    }
    gw.context.update(payload)

    if categories:
        summary = ", ".join(f"{name} ({len(words)})" for name, words in categories.items())
        gw.info(f"Configured {len(categories)} category set(s): {summary}")
    else:
        gw.warning("No categories detected; all transcripts will use the fallback label")

    return payload


def _recognize_audio(
    recognizer: sr.Recognizer,
    audio_data: sr.AudioData,
    *,
    engine: str,
    language: str,
) -> tuple[str, str, str | None]:
    requested = engine.lower()
    if requested not in {"auto", "google", "sphinx"}:
        raise ValueError("engine must be 'google', 'sphinx' or 'auto'")

    engines = ("sphinx", "google") if requested == "auto" else (requested,)
    last_error: str | None = None

    for candidate in engines:
        try:
            if candidate == "google":
                transcript = recognizer.recognize_google(audio_data, language=language)
            else:
                transcript = recognizer.recognize_sphinx(audio_data, language=language)
            return transcript, candidate, None
        except sr.UnknownValueError:
            return "", candidate, "unknown-value"
        except sr.RequestError as exc:
            last_error = f"request-error: {exc}"
            if requested == "auto":
                continue
            return "", candidate, last_error

    return "", engines[-1], last_error


def _classify_transcript(
    transcript: str,
    categories: Mapping[str, Iterable[str]],
    *,
    fallback: str,
) -> tuple[str, dict[str, list[str]]]:
    normalized = transcript.lower()
    matches: dict[str, list[str]] = {}
    best_label: str | None = None
    best_score = 0

    for name, descriptors in categories.items():
        matched = [token for token in descriptors if token and token in normalized]
        if matched:
            matches[name] = matched
            score = len(matched)
            if score > best_score:
                best_label = name
                best_score = score

    if best_label is None:
        return fallback, matches
    return best_label, matches


def listen(
    *,
    language: str = "en-US",
    engine: str = "auto",
    pause: float | str = 0.8,
    phrase: float | str | None = None,
    rest: float | str = 0.0,
    energy: float | str | None = None,
    ambient: float | str = 0.5,
    dynamic: bool | str = True,
    timeout: float | str | None = None,
    once: bool | str = False,
    categories: Mapping[str, Iterable[str]] | None = None,
    default: str | None = None,
    unknown: str | None = None,
) -> dict[str, object]:
    """Continuously capture speech and classify transcripts into categories."""

    pause_threshold = _coerce_float(pause, default=0.8) or 0.8
    phrase_limit = _coerce_float(phrase)
    rest_interval = _coerce_float(rest, default=0.0) or 0.0
    ambient_duration = _coerce_float(ambient, default=0.5)
    timeout_value = _coerce_float(timeout)
    once_value = _coerce_bool(once)
    dynamic_value = _coerce_bool(dynamic)

    if pause_threshold <= 0:
        raise ValueError("pause must be a positive duration")
    if rest_interval < 0:
        raise ValueError("rest must be zero or a positive duration")
    if phrase_limit is not None and phrase_limit <= 0:
        raise ValueError("phrase must be a positive duration when provided")
    if timeout_value is not None and timeout_value <= 0:
        raise ValueError("timeout must be a positive duration when provided")

    if categories is None:
        categories = gw.context.get("transcriptor_categories") or {}
    default_label = default or gw.context.get("transcriptor_category_default", "uncategorized")
    unknown_label = unknown or gw.context.get("transcriptor_category_unknown", default_label)

    recognizer = sr.Recognizer()
    recognizer.pause_threshold = pause_threshold
    recognizer.dynamic_energy_threshold = dynamic_value
    if energy is not None:
        energy_value = _coerce_float(energy)
        if energy_value is not None and energy_value > 0:
            recognizer.energy_threshold = energy_value

    try:
        microphone = sr.Microphone()
    except OSError as exc:  # pragma: no cover - requires audio hardware
        raise RuntimeError("No microphone input device is available") from exc

    gw.info("Starting live transcription loop")
    summary: dict[str, object] = {}

    with microphone as source:  # pragma: no cover - hardware dependent
        if ambient_duration and ambient_duration > 0:
            gw.info(f"Calibrating ambient noise for {ambient_duration:.2f}s")
            recognizer.adjust_for_ambient_noise(source, duration=ambient_duration)

        running = True
        while running:
            gw.info("Listening for speech...")
            try:
                audio_data = recognizer.listen(
                    source,
                    timeout=timeout_value,
                    phrase_time_limit=phrase_limit,
                )
            except sr.WaitTimeoutError:
                gw.debug("Timed out waiting for speech; retrying")
                if once_value:
                    break
                continue

            transcript, used_engine, error = _recognize_audio(
                recognizer,
                audio_data,
                engine=engine,
                language=language,
            )

            if not transcript:
                if error:
                    gw.warning(f"Recognition error via {used_engine}: {error}")
                else:
                    gw.info(f"No speech detected via {used_engine}")
                if once_value:
                    running = False
                continue

            label, match_map = _classify_transcript(
                transcript,
                categories,
                fallback=unknown_label,
            )

            matched_terms = match_map.get(label, [])
            if matched_terms:
                match_text = ", ".join(matched_terms)
                gw.info(f"Matched category '{label}' via: {match_text}")
            else:
                gw.info(f"Classified transcript as '{label}' (no keyword match)")

            print(f"[{label}] {transcript}")

            summary = {
                "transcriptor_transcript": transcript,
                "transcriptor_category": label,
                "transcriptor_matches": match_map,
                "transcriptor_engine": used_engine,
            }
            gw.context.update(summary)
            gw.results.insert("transcriptor", summary)

            if once_value:
                running = False
            elif rest_interval:
                time.sleep(rest_interval)

    return summary
