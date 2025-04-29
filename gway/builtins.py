import os
import sys
import logging

from contextlib import contextmanager

logger = logging.getLogger(__name__)


VERBOSE = False
_print = print  # Store original print


def print(*args, **kwargs):
    """Custom print function to handle verbose output."""
    message = " ".join(str(arg) for arg in args)
    logger.info(message)
    # Check if we should use the original print or verbose option in kwargs
    if VERBOSE or kwargs.pop("verbose", False):
        kwargs.pop("args", None)  
        kwargs.pop("kwargs", None)
        _print(message, **kwargs)  # Pass the message as args, use kwargs for other options
    else:
        _print(message)  # Only print the message



def verbose(value: bool = None):
    """Set verbose mode or use as a context manager."""

    global VERBOSE

    if value is not None:
        VERBOSE = value
        if VERBOSE:
            logger.setLevel(logging.DEBUG)
            logger.debug("Verbose mode enabled.")
        else:
            logger.setLevel(logging.INFO)
            logger.debug("Verbose mode disabled.")
        return VERBOSE
    else:
        class VerboseContext:
            def __enter__(self):
                self._original = VERBOSE
                verbose(True)
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                verbose(self._original)

            def __repr__(self):
                return str(VERBOSE)

        return VerboseContext()
    

def version() -> str:
    """Return the version of the package."""
    # Get the version in the VERSION file
    from .core import BASE_PATH
    version_path = os.path.join(BASE_PATH, "VERSION")
    if os.path.exists(version_path):
        with open(version_path, "r") as version_file:
            version = version_file.read().strip()
            logger.info(f"Current version: {version}")
            return version
    else:
        logger.error("VERSION file not found.")
        return "unknown"
    

def abort(message: str, exit_code: int = 1):
    """Abort with error message."""
    from .core import LIBRARY_MODE
    logger.error(message)
    print(f"Error: {message}")
    
    # Check if we are running in test mode by checking an environment variable
    if os.getenv('TEST_MODE') != '1':  # Only call sys.exit if TEST_MODE is not set
        if not LIBRARY_MODE:
            sys.exit(exit_code)
        else:
            raise SystemExit(exit_code)
    else:
        # In test mode, just print the error and don't exit
        print(f"Test mode: {message} (exit code {exit_code})")
        return exit_code


def hello_world():
    """Print 'Hello, World!'."""
    print("Hello, World!")

