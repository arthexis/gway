Running Tests
-------------

Install the runtime dependencies first. The simplest approach is:

.. code-block:: bash

   pip install -r requirements.txt
   pip install -e .
   pytest -q

This ensures that modules such as ``requests`` and ``websockets`` are
available to the test suite.
