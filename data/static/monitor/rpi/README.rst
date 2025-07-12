Raspberry Pi Utilities
----------------------

The ``monitor.rpi`` project contains helpers for Raspberry Pi management.
The primary command ``ru`` clones the currently running system to
another microSD card using ``dd``.

Usage
=====

From the command line::

    gway monitor.rpi ru /dev/sda

Programmatically::

    from gway import gw
    gw.monitor.rpi.ru('/dev/sda')

Ensure the destination device refers to the USB microSD writer
connected to the Pi.  The entire device will be overwritten and
requires ``sudo`` permissions.  Cloning may take several minutes.

Web Interface
=============

Launch the web application and open ``/monitor/rpi/pi-remote`` to use a simple
interface for selecting the target device and starting the copy.  The
progress bar updates automatically while the clone runs.
