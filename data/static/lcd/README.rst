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

   Alternatively install the pure Python ``smbus2`` package:

   .. code-block:: bash

      pip install gway[lcd]
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
    gway lcd show "Scrolling text" --scroll 2
    gway lcd show "Temporary" --hold 5
    gway lcd show "Long message that needs wrapping" --wrap
    gway lcd show "Long scrolling message" --scroll 0.5 --wrap
    gway lcd show "Proportional" --scroll 0.1 --ratio 2
    gway lcd brightness off

Install a boot message shown once at startup::

    gway lcd boot "Welcome"

Remove the boot message::

    gway lcd boot --remove

``--scroll`` accepts the delay in seconds between each scroll step (``0``
disables scrolling). ``--hold`` shows the message for the given number of
seconds and then restores the previous message stored in ``work/lcd-last.txt``.
``--wrap`` word-wraps long messages over the two 16-character lines of the
display and can be combined with ``--scroll`` to snake text across both lines.
``--ratio`` divides the scrolling speed of the top row and multiplies that of
the bottom row so both rows show the same message at proportional speeds.
Message text may include ``[sigils]`` that are resolved before display.

``brightness`` toggles the backlight of the standard PCF8574 backpack on or
off.  The hardware only exposes a digital control line so intermediate
brightness levels are not available.

Programmatically::

    from gway import gw
    gw.context["USER"] = "world"
    gw.lcd.show("Hello [USER]\nWorld")
    gw.lcd.show("Scrolling", scroll=0.5)
    gw.lcd.show("Temp", hold=3)
    gw.lcd.show("A long message that should wrap", wrap=True)
    gw.lcd.show("Snaking message", scroll=0.5, wrap=True)
    gw.lcd.show("Proportional", scroll=0.1, ratio=2)
    gw.lcd.brightness("on")
    gw.lcd.boot("Hello")
    gw.lcd.boot(remove=True)
