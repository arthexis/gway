Running Tests
-------------

Install the runtime dependencies first. The simplest approach is:

.. code-block:: bash

   pip install -r requirements.txt
   pip install -e .
   gway test --coverage

Security scanning is part of the continuous integration pipeline. To replicate
the checks locally run:

.. code-block:: bash

   bandit -q -r gway projects

The ``gway test`` command accepts ``--install`` to perform these
installation steps automatically. When dependencies like ``requests``
are missing, ``--install`` is run implicitly.

This ensures that modules such as ``requests`` are available to the test
suite.

Enabling Optional Tests
-----------------------

Some tests are skipped by default, such as those that capture screenshots. You
can enable them by passing feature flags to ``gway test``:

.. code-block:: bash

   gway test --flags screen

The flags are stored in the ``GW_TEST_FLAGS`` environment variable, which test
cases can check via ``is_test_flag('flag')``.

To list all available flags, run:

.. code-block:: bash

   gway help --list-flags

Importing Project Modules
-------------------------

Tests should access project code via the ``gw`` dispatcher whenever possible:

.. code-block:: python

   from gway import gw
   result = gw.help('hello-world')

This mirrors real-world usage and avoids fragile import paths.  When a test
needs to call private helpers that are not exposed through ``gw``, load the
module lazily during ``setUpClass`` using a small helper:

.. code-block:: python

   class MyTests(unittest.TestCase):
       @staticmethod
       def _load_mod():
           import importlib.util
           from pathlib import Path

           spec = importlib.util.spec_from_file_location(
               "mod", Path(__file__).resolve().parents[1] / "projects" / "mod.py"
           )
           module = importlib.util.module_from_spec(spec)
           spec.loader.exec_module(module)
           return module

       @classmethod
       def setUpClass(cls):
           cls.mod = cls._load_mod()
