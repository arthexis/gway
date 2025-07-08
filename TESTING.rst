Running Tests
-------------

Install the runtime dependencies first. The simplest approach is:

.. code-block:: bash

   pip install -r requirements.txt
   pip install -e .
   gway test --coverage

This ensures that modules such as ``requests`` and ``websockets`` are
available to the test suite.

Enabling Optional Tests
-----------------------

Some tests are skipped by default, such as those that capture screenshots. You
can enable them by passing feature flags to ``gway test``:

.. code-block:: bash

   gway test --flags screenshot

The flags are stored in the ``GW_TEST_FLAGS`` environment variable, which test
cases can check via ``is_test_flag('flag')``.
