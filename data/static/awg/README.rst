AWG Cable Calculator
--------------------

The ``awg`` project provides helpers for selecting electrical cable sizes using
American Wire Gauge tables.  It exposes a ``find_awg`` function and a small web
form so you can determine the required cable, voltage drop and conduit size
straight from the command line or a browser.

Usage
=====

From the command line::

    gway awg find-awg --meters 30 --amps 60

Programmatically::

    from gway import gw
    result = gw.awg.find_awg(meters=30, amps=60)
    print(result["awg"])

The helper returns a dictionary with fields like ``awg`` (gauge), ``lines``,
``total_meters``, voltage drop and other metadata.  When no cable satisfies a
3%% drop limit the result contains ``{"awg": "n/a"}`` and may include a
``warning`` message.

Parameters
==========

``find_awg`` accepts several keyword arguments:

``meters``
  Cable length in meters (required).
``amps``
  Load in amperes, default ``40``.
``volts``
  System voltage, default ``220``.
``material``
  ``"cu"`` for copper or ``"al"`` for aluminium.
``max_awg``
  Limit the thickest cable allowed.  Values may use ``1/0`` style notation.
``max_lines``
  Maximum number of line conductors.
``phases``
  ``1`` or ``3`` phase AC systems (``2`` is treated as two phases).
``temperature``
  Conductor temperature rating: ``60``/``75``/``90``. Default is ``60``.
``conduit``
  If provided the result includes the minimum trade size for ``emt``, ``imc``,
  ``rmc`` or ``fmc`` conduit.
``ground``
  Number of ground wires per line.

Additional Tools
================

``find_conduit``
  Utility to calculate conduit diameter for a given AWG and number of cables.
``view_awg_calculator``
  Renders ``/awg/awg-calculator`` – an HTML form backed by ``find_awg`` for quick
  calculations in the browser.

Data Files
==========

The calculations rely on two CSV tables located under ``data/awg``:

``cable_size.csv``
  Base cable properties and ampacities.
``conduit_fill.csv``
  Maximum cable counts per conduit size and type.

