GWAY
====

**GWAY** is a dynamic CLI and function-dispatch framework that allows you to invoke and chain Python functions from your own projects or built-ins, with automatic context resolution, argument injection, and environment support.

Higher-level programming, lower barrier to entry.

Features
--------

- 🔌 Seamless function calling from CLI or code (e.g., ``gway.awg.find_cable()``)
- ⛓️ CLI chaining support: ``func1 - func2`` or ``func1 ; func2``
- 🧠 Sigil-based context resolution (e.g., ``[result_key]``)
- ⚙️ Automatic CLI argument generation, with support for ``*args`` and ``**kwargs``
- 🧪 Built-in test runner: ``gway test``
- 📦 Environment-aware loading (e.g., ``clients``, ``servers``)

Example: AWG Cable Calculation
------------------------------

Given a project ``awg.py`` containing logic to calculate cable sizes and conduit requirements:

**Call from Python**

.. code-block:: python

    from gway import Gateway

    gway = Gateway()
    result = gway.awg.find_cable(meters=30, amps=60, material="cu", volts=240)
    print(result)

**Call from CLI**

.. code-block:: bash

    # Basic cable sizing
    gway awg find-cable --meters 30 --amps 60 --material cu --volts 240

    # With conduit calculation
    gway awg find-cable --meters 30 --amps 60 --material cu --volts 240 --conduit emt

**Chaining Example**

.. code-block:: bash

    # Chain cable calculation and echo the result
    gway awg find-cable --meters 25 --amps 60 - print --text "[awg]"

Project Structure Expectations
------------------------------

- Project functions should reside in Python modules within the root directory.
- Environments should be stored under ``envs/clients/`` and ``envs/servers/``.
- Shared resources like database connections should be accessed through the injected ``Gateway()`` instance.

Installation
------------

.. code-block:: bash

    pip install gway  # or install from local source

License
-------

MIT License
