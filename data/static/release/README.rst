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

Marking PRs for Release
=======================

Instead of running the release command locally, a pull request labeled
``release`` can generate a new version. When such a PR is merged the
``auto-release`` workflow runs ``gw.release.build --bump --git --tag`` on the
main branch. The workflow commits the version bump, tags it (``vX.Y.Z``) and
pushes the result, which in turn triggers the ``test-release`` workflow above.
