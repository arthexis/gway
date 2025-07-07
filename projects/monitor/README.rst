Network Manager Monitor
-----------------------

The ``monitor.nmcli`` project can manage WiFi connections automatically. Set ``AP_SSID`` and ``AP_PASSWORD`` in your environment to define the access point. Optionally use ``AP_GATEWAY`` to override the default ``10.42.0.1`` hotspot address. Start the watcher from a recipe with:

.. code-block:: text

    monitor start-watch nmcli

