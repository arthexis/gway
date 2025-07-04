OCPP Components
---------------

``projects/ocpp`` contains a minimal OCPP 1.6 demo implementation.
The submodules are:

- ``csms`` – a simple Central System with a status dashboard.
- ``evcs`` – a charge point simulator that connects to ``csms``.
- ``sink`` – a message logger for debugging.

Launch a simulator session pointing at your CSMS with:

.. code-block:: bash

   gway ocpp.evcs simulate --host 127.0.0.1 --ws-port 9000 --cp-path CPX

Open ``/ocpp/csms/charger-status`` in your browser to view all
connected chargers. Each card refreshes every few seconds so data
stays current. Click a charger to open its detail page where you can
send commands like ``Stop`` or ``Soft Reset`` and watch the log update
in real time. The auto-refresh will collapse any open panels; you can
temporarily disable it by removing the ``data-gw-refresh`` attribute
from the page.

Etron Recipes
-------------

``recipes/etron`` contains GWAY recipes used in real EV charging
demos:

- ``local.gwr`` – start both the CSMS dashboard and a simulator on the
  same machine for quick testing.
- ``cloud.gwr`` – run a CSMS instance for cloud deployments with an
  optional RFID allow list.

Run them via ``gway run <recipe>``. For example:

.. code-block:: bash

   gway run recipes/etron/local.gwr

OCPP Data Storage
-----------------

``ocpp.data`` provides helper functions to persist transactions, meter
values and error reports in ``work/ocpp.sqlite`` using ``gw.sql``.  The
``csms`` module calls these helpers so charging sessions are recorded
automatically.

Both the server time and the charger-provided timestamp are stored for
each transaction event. This lets you verify the charger's clock during
reconciliation.

To review stored information you can render a simple summary table with:

.. code-block:: bash

   gway ocpp.data.view_charger_summary

This shows the number of sessions and total energy per charger along
with the timestamp of the last stop and any last recorded error.

Two additional views provide more insight into stored data:

``view_charger_details`` displays transaction records for one charger
with simple filtering and pagination. ``view_time_series`` returns a
chart of energy usage over time for selected chargers and dates.

