RFID Utilities
--------------

``projects/rfid`` offers helpers for working with RFID hardware.

``scan`` – wait for a card to be scanned and print its information. Press any
key to stop scanning or pass ``--wait`` to exit automatically after the
specified number of seconds. Provide ``--block`` to read a specific block or
``--deep`` to iterate through the first 64 blocks of a MIFARE Classic card.
Authentication keys may be supplied via ``--key-a`` or ``--key-b``; when
neither is provided the tool automatically tries common manufacturer defaults
and reports which one worked.

``pinout`` – return the expected wiring between the MFRC522 board and a
Raspberry Pi.

Wiring reference
~~~~~~~~~~~~~~~~

The RFID helpers expect the reader to be connected following the default
``SimpleMFRC522`` pinout:

.. list-table::
   :header-rows: 1

   * - RFID pin
     - Raspberry Pi connection
   * - SDA
     - CE0 (GPIO8, physical pin 24)
   * - SCK
     - SCLK (GPIO11, physical pin 23)
   * - MOSI
     - MOSI (GPIO10, physical pin 19)
   * - MISO
     - MISO (GPIO9, physical pin 21)
   * - IRQ
     - GPIO4 (physical pin 7)
   * - GND
     - GND (physical pin 6)
   * - RST
     - GPIO25 (physical pin 22)
   * - 3v3
     - 3V3 (physical pin 1)

Bringing the reader online
~~~~~~~~~~~~~~~~~~~~~~~~~~

The MFRC522 driver expects the Raspberry Pi's first SPI controller (``bus 0``)
to be enabled and exposed as ``/dev/spidev0.0``. If ``gway rfid scan`` reports
that the SPI device is missing:

* enable SPI via ``sudo raspi-config nonint do_spi 0`` (or through
  ``raspi-config`` → *Interface Options* → *SPI*)
* confirm ``dtparam=spi=on`` exists in ``/boot/config.txt`` and reboot
* ensure the ``spi_bcm2835`` kernel module is loaded (``lsmod | grep spi``)
* add your user to the ``spi`` group or run the command with ``sudo`` if
  permissions are denied

Other single-board computers may expose the device under a different
``/dev/spidevX.Y`` path. Move the reader to the chip select that maps to
``spidev0.0`` or extend ``projects/rfid.scan`` to pass a custom bus/device pair
to the MFRC522 driver.
