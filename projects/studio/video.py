"""Video stream helpers for studio project."""

from __future__ import annotations

from typing import Iterator, Iterable
from gway import gw


def capture_camera(*, source: int = 0) -> Iterator:
    """Capture frames from a camera device.

    Parameters
    ----------
    source:
        Camera index passed to ``cv2.VideoCapture``. Defaults to ``0``.

    Returns
    -------
    Iterator
        Generator yielding frames as numpy arrays. The capture device is
        released automatically when iteration stops.
    """
    import cv2

    gw.debug(f"Opening camera source {source}")
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera {source}")

    def _generator() -> Iterator:
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                yield frame
        finally:
            cap.release()
            gw.debug("Camera released")

    return _generator()


def display_video(stream: Iterable, *, screen: int = 0) -> bool:
    """Display frames from ``stream`` using pygame.

    Parameters
    ----------
    stream:
        An iterable yielding numpy array frames (H x W x 3, BGR).
    screen:
        Screen index (currently unused, placeholder for multi-screen setups).

    Returns
    -------
    bool
        ``True`` when the stream is consumed without errors.
    """
    if not hasattr(stream, "__iter__"):
        raise ValueError("stream must be an iterable of frames")

    import numpy as np  # noqa: F401 - only for type expectations
    import cv2
    import pygame

    iterator = iter(stream)
    try:
        first = next(iterator)
    except StopIteration:
        return True

    height, width = first.shape[:2]
    pygame.init()
    window = pygame.display.set_mode((width, height))

    def _show(frame):
        surf = pygame.surfarray.make_surface(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        window.blit(surf, (0, 0))
        pygame.display.flip()

    try:
        _show(first)
        for frame in iterator:
            _show(frame)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return True
        return True
    finally:
        pygame.quit()
