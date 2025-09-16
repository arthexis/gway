Raspberry Pi Utilities (Removed)
--------------------------------

The original ``rpi`` project exposed a helper named ``ru`` that cloned the
running system image to another block device using ``dd``. Because the
command performed privileged disk operations without confirmation it has been
removed for safety. New development should provide external safeguards before
reintroducing similar functionality.
