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

