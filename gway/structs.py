# file: gway/structs.py

import threading
import collections
from types import SimpleNamespace


class Results(collections.ChainMap):
    """ChainMap-based result collector for Gateway function calls."""
    
    # Use thread-local storage to store results for each thread
    _thread_local = threading.local()
    
    def __init__(self):
        """Initialize the ChainMap with thread-local storage."""
        if not hasattr(self._thread_local, 'maps'):
            self._thread_local.maps = [{}]  # Initialize an empty dict for the current thread
        
        # Call the parent constructor with the thread-local storage map
        super().__init__(*self._thread_local.maps)
    
    def insert(self, func_name, value):
        """Insert a value into the result storage."""
        if isinstance(value, dict):
            self.maps[0].update(value)
        else:
            self.maps[0][func_name] = value

    def get(self, key, default=None):
        """Retrieve a value by key from the top of the chain."""
        return self.maps[0].get(key, default)
    
    def pop(self, key, default=None):
        """Remove and return a value by key from the top of the chain."""
        return self.maps[0].pop(key, default)
    
    def clear(self):
        """Clear the current thread-local map."""
        self.maps[0].clear()
    
    def update(self, *args, **kwargs):
        """Update the current map with another dictionary or key-value pairs."""
        self.maps[0].update(*args, **kwargs)
    
    def keys(self):
        """Return the keys of the current map."""
        return self.maps[0].keys()
    
    def get_results(self):
        """Return the current results stored for the thread."""
        return self.maps[0]
    

class Project(SimpleNamespace):
    def __init__(self, name, funcs, gateway):
        """
        A stub representing a project namespace. Holds available functions
        and raises an error when called without an explicit function.
        """
        super().__init__(**funcs)
        self._gateway = gateway
        self._name = name
        # _default_func is no longer used for guessing
        self._default_func = None

    def __call__(self, *args, **kwargs):
        """
        When the project object itself is invoked, list all available
        functions and abort with an informative error, instead of guessing.
        """
        from gway import gw
        from gway.console import show_functions

        # Gather all callables in this namespace
        functions = {
            name: func
            for name, func in self.__dict__.items()
            if callable(func)
        }

        # Display available functions to the user
        show_functions(functions)


class Null:
    # aka. The Black Hole Structure
    def __call__(self, *args, **kwargs):
        return self

    def __bool__(self):
        return False

    def __str__(self):
        return "Null"

    def __repr__(self):
        return "Null"

    def __getattr__(self, name):
        return self

    def __setattr__(self, name, value):
        pass

    def __getitem__(self, key):
        return self

    def __setitem__(self, key, value):
        pass

    def __iter__(self):
        return iter(())

    def __next__(self):
        raise StopIteration

    def __len__(self):
        return 0

    def __eq__(self, other):
        return isinstance(other, Null)

    def __ne__(self, other):
        return not isinstance(other, Null)

    def __contains__(self, item):
        return False

    # Absorb arithmetic and other operators
    def __add__(self, other): return self
    def __radd__(self, other): return self
    def __sub__(self, other): return self
    def __rsub__(self, other): return self
    def __mul__(self, other): return self
    def __rmul__(self, other): return self
    def __truediv__(self, other): return self
    def __rtruediv__(self, other): return self
    def __floordiv__(self, other): return self
    def __rfloordiv__(self, other): return self
    def __mod__(self, other): return self
    def __rmod__(self, other): return self
    def __pow__(self, other): return self
    def __rpow__(self, other): return self

    # Comparisons
    def __lt__(self, other): return False
    def __le__(self, other): return False
    def __gt__(self, other): return False
    def __ge__(self, other): return False

    # Context management
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): return False

    # Async support
    async def __aenter__(self): return self
    async def __aexit__(self, exc_type, exc_val, exc_tb): return False

    def __await__(self):
        async def dummy(): return self
        return dummy().__await__()

null = Null()
Null = null


# TODO: Create a new Apeiron class that will hold "conversion" functions
# Apeiron should be designed as a Mixin for Gateway. Its methods will be
# to_html, to_list, to_yaml, etc. This will free space from gway/builtins.py
