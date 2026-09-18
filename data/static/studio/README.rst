Studio Project
--------------

The ``studio`` project groups multimedia helpers under a single namespace. Subprojects include ``screen`` for screenshots and display tools, ``mic`` for audio recording, ``clip`` for clipboard utilities and ``qr`` for QR code generation.

``screen.display`` shows an image file using the default viewer. When no path
is provided, it locates the most recent image within the ``work`` directory;
use ``--before`` with an ISO-like timestamp to select the latest image before a
given time.
