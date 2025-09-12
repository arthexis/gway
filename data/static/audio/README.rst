Audio Utilities
---------------

The ``audio`` project provides simple helpers to record audio from the
microphone and play it back.

Functions
=========

``record``
  Capture audio from the default input device. The recording is saved to a
  ``.wav`` file in the ``work/`` directory by default. You may customise the duration,
  format (currently ``wav`` only) and target filename. By default the user is
  prompted to press Enter before recording starts; use ``--immediate`` to begin
  right away.

``playback``
  Play a ``.wav`` file. When invoked with ``--loop`` it keeps the audio
  playing in the background using Gateway's async services.

Usage
=====

Record five seconds of audio and play it back::

    gway audio record --duration 5 --immediate
    gway audio playback --audio "$(gw results audio.record)"

Or chain the commands, omitting the project name and relying on auto
injection::

    gway audio record --duration 5 --immediate - playback

To keep a file playing in the background::

    gway audio playback --audio song.wav --loop
