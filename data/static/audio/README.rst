Audio Utilities
---------------

The ``audio`` project provides simple helpers to record audio from the
microphone and play it back.

Functions
=========

``record``
  Capture audio from the default input device. The recording is saved to a
  ``.wav`` file in the working directory. You may customise the duration,
  format (currently ``wav`` only) and target filename.

``playback``
  Play a ``.wav`` file. When invoked with ``--loop`` it keeps the audio
  playing in the background using Gateway's async services.

Usage
=====

Record five seconds of audio and play it back::

    gway audio record --duration 5
    gway audio playback --audio "$(gw results audio.record)"

Or chain the commands, omitting the project name on the second call::

    gway audio record --duration 5 - playback --audio "$(gw results audio.record)"

To keep a file playing in the background::

    gway audio playback --audio song.wav --loop
