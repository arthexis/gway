import sys
import logging


logger = logging.getLogger(__name__)


VERBOSE = False
_print = print  # Store original print


def print(*args, **kwargs):
    """Custom print function to handle verbose output."""
    message = " ".join(str(arg) for arg in args)
    logger.info(message)
    if VERBOSE or kwargs.pop("verbose", False):
        _print(*args, **kwargs)


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


def version() -> str:
    """Return the version of the package."""
    return "0.1.0"


def abort(message: str, exit_code: int = 1):
    """Abort with error message."""
    logger.error(message)
    print(f"Error: {message}")
    sys.exit(exit_code)


def hello_world():
    """Print 'Hello, World!'."""
    print("Hello, World!")

