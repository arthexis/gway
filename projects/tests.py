# projects/tests.py

# This module contains functions that are useful to test against
# However, it doesn't implement the test runner functionality itself
# See the builtins module for test() instead


# A dummy function for testing dynamic loading
def dummy_function(param1: str, param2: str = "default"):
    """Dummy function for testing."""
    return {"result": f"{param1}-{param2}"}

# Function accepting *args
def variadic_positional(*args):
    return {"args": args}

# Function accepting **kwargs
def variadic_keyword(**kwargs):
    return {"kwargs": kwargs}

# Function accepting both *args and **kwargs
def variadic_both(*args, **kwargs):
    return {"args": args, "kwargs": kwargs}


def view_index():
    return {"greeting": "Hello World!"}
