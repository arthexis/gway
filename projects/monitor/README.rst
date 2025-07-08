Network Manager Monitor
-----------------------

The ``monitor.nmcli`` project collects network information using ``nmcli``.
It does not alter any connections automatically. Serve the watcher from a recipe with:

.. code-block:: text

    monitor serve-watch nmcli

Use the ``run`` page in the web interface to execute arbitrary ``nmcli`` commands when needed.

