RFID Utilities
--------------

``projects/rfid`` offers helpers for working with RFID hardware.

``scan`` – wait for a card to be scanned and print its information. Press any
key to stop scanning.

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
