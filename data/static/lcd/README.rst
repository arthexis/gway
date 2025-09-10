LCD
---

Utilities for driving a 16×2 character LCD with an I²C backpack.

Setup
=====

1. Enable the I²C interface:

   ``sudo raspi-config`` → Interface Options → **I2C** → Enable
2. Install the required packages:

   .. code-block:: bash

      sudo apt-get update
      sudo apt-get install -y i2c-tools python3-smbus
3. (Optional) allow running without ``sudo``:

   .. code-block:: bash

      sudo adduser pi i2c
      sudo reboot

Wire the backpack's ``VCC`` to 5V, ``GND`` to ground, ``SDA`` to GPIO2 and
``SCL`` to GPIO3.

Usage
=====

From the command line::

    gway lcd show "Hello world"
    gway lcd show "Hello [USER]"
    gway lcd show "Scrolling text" --scroll
    gway lcd show "Fast" --scroll --ms 500

``--scroll`` moves the message across the first line of the display.
The ``--ms`` option changes the speed (milliseconds per character, default
2000).  Message text may include ``[sigils]`` that are resolved before
display.

Programmatically::

    from gway import gw
    gw.context["USER"] = "world"
    gw.lcd.show("Hello [USER]\nWorld")
    gw.lcd.show("Scrolling", scroll=True, ms=500)
