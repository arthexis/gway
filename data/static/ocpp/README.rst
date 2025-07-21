OCPP Components
---------------

``projects/ocpp`` contains a minimal OCPP 1.6 demo implementation.
The submodules are:

- ``csms`` – a simple Central System with a status dashboard.
- ``evcs`` – a charge point simulator that connects to ``csms``.
- ``sink`` – a message logger for debugging.
- ``rfid`` – helpers for RFID allow/deny checks.

The landing page ``/ocpp/ocpp-dashboard`` shows a quick summary of these
sub‑projects. When mounting the dashboard with ``web.app.setup_app`` the CSMS
views and renders are discovered automatically because sub‑projects are treated
as delegate modules under the ``/ocpp`` path.

Launch a simulator session pointing at your CSMS with:

.. code-block:: bash

   gway ocpp.evcs simulate \
       --host 127.0.0.1 --ws-port 9000 \
       --cp-path ocpp/csms/CPX

The simulator can also be controlled via the web UI at
``/ocpp/evcs/cp-simulator`` (call ``gw.ocpp.evcs.view_simulator``).

The simulator accepts ``--kwh-min`` and ``--kwh-max`` to control the
approximate energy delivered per session. For example, ``--kwh-min 40
--kwh-max 70`` will produce sessions around 40–70 kWh. Use ``--interval``
to specify how often MeterValues are sent (default 5s). The
``--pre-charge-delay`` option keeps the charger idle for the given
number of seconds after connecting while it sends Heartbeats and idle
MeterValues.

Open ``/ocpp/csms/active-chargers`` in your browser to view all
connected chargers. Each card refreshes every few seconds so data
stays current. Click a charger to open its detail page where you can
send commands like ``Stop`` or ``Soft Reset`` and watch the log update
in real time. The auto-refresh will collapse any open panels; you can
temporarily disable it by removing the ``gw-refresh`` attribute
from the page.

The charger detail view also lists recent transactions. By default it
shows the last 24 hours but you can adjust the period with the date
selectors above the table.

Etron Recipes
-------------

``recipes/etron`` contains GWAY recipes used in real EV charging
demos:

- ``local.gwr`` – start both the CSMS dashboard and a simulator on the
  same machine for quick testing.
- ``cloud.gwr`` – run a CSMS instance for cloud deployments. Use
  ``ocpp.rfid.approve`` with a CDV table to control RFID access.
- ``local_proxy.gwr`` – run a local CSMS that forwards unknown requests
  to a remote instance. This keeps sessions operational when offline and
  syncs with the cloud once connectivity returns.

Run them via ``gway run <recipe>``. For example:

.. code-block:: bash

   gway run recipes/etron/local.gwr

The integration suite includes ``tests/test_proxy_fallback.py`` which
starts both the local and cloud recipes to verify that requests are
proxied once the cloud is available. Enable it with the ``proxy`` test
flag. This harness can serve as a template for offline-first
deployments.

OCPP Data Storage
-----------------

``ocpp.data`` provides helper functions to persist transactions, meter
values and error reports in ``work/ocpp.db`` using ``gw.sql``. By
default these helpers rely on the DuckDB engine so the ``duckdb``
package must be available. The ``csms`` module calls these helpers so
charging sessions are recorded automatically.

For comparison with real EVCS logs, every completed transaction is also
written as a ``.dat`` file under ``work/ocpp/records/<charger_id>/``.

Both the server time and the charger-provided timestamp are stored for
each transaction event. This lets you verify the charger's clock during
reconciliation.

To review stored information you can render a simple summary table with:

.. code-block:: bash

   gway ocpp.data.view_charger_summary

The same information is available from the web route
``/ocpp/charger-summary``.

This shows the number of sessions and total energy per charger along
with the timestamp of the last stop and any last recorded error.

Two additional views provide more insight into stored data:

``view_charger_details`` displays transaction records for one charger
with simple filtering and pagination. ``view_time_series`` returns a
chart of energy usage over time for selected chargers and dates.


RFID Management
---------------

RFID access entries are stored in ``work/ocpp/rfids.cdv``. Open
``/ocpp/manage-rfids`` in your browser to edit these records. The page lists
all tags with their balance and ``allowed`` flag so you can quickly update,
credit or delete entries and add new ones.
