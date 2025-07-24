Release Utilities
-----------------

Scripts for building distributions and uploading them to package indexes.

Tagging Builds
==============

``gw.release.build`` accepts a ``--tag`` option that creates and pushes a git
tag after the build completes. The tag name corresponds to the package version
(e.g. ``v1.2.3``). This is typically used for release testing without uploading
to PyPI::

   gway release build --bump --git --tag

GitHub will run the ``test-release`` workflow on every pushed tag and mark a
successful run as ready for release to PyPI.
