import os
import sys
import logging

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


def verbose(value: bool = True):
    """Set verbose mode."""
    global VERBOSE
    VERBOSE = value
    if VERBOSE:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose mode enabled.")
    else:
        logger.setLevel(logging.INFO)
        logger.debug("Verbose mode disabled.")
    return VERBOSE  # Ensure it returns the current verbose state


def version() -> str:
    """Return the version of the package."""
    return "0.1.0"


def abort(message: str, exit_code: int = 1):
    """Abort with error message."""
    logger.error(message)
    print(f"Error: {message}")
    
    # Check if we are running in test mode by checking an environment variable
    if os.getenv('TEST_MODE') != '1':  # Only call sys.exit if TEST_MODE is not set
        sys.exit(exit_code)
    else:
        # In test mode, just print the error and don't exit
        print(f"Test mode: {message} (exit code {exit_code})")


def hello_world():
    """Print 'Hello, World!'."""
    print("Hello, World!")

