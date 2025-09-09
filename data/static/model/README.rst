Django Model Bridge
-------------------

The ``model`` project exposes Django models from the `Arthexis`_ application
through the ``gway`` CLI. All models from every installed app are merged into a
single namespace so you never have to specify the originating app. Models are
resolved on demand and their methods can be invoked directly. If multiple apps
define a model with the same class name a warning is issued and the first model
found is used.

Usage
=====

From the command line::

    gway model energy-account generate-report --params

For convenience the project may also be referenced as ``mod`` or the percent
symbol (``%``)::

    gway % energy-account generate-report

Environment
===========

If ``DJANGO_SETTINGS_MODULE`` isn't defined the project will try to import
``arthexis.settings`` or ``config.settings`` and use whichever is available.
Set the variable explicitly to use a different settings module.

.. _Arthexis: https://github.com/arthexis/arthexis
