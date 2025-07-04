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

Open ``/ocpp/csms/charger-status`` in your browser and you can send
``Stop`` or ``Soft Reset`` commands to see the simulator react.

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
