import functools
import importlib
import subprocess
import logging
import sys
import re

logger = logging.getLogger(__name__)


def requires(*packages):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for package_spec in packages:
                # Extract package name for import checking
                pkg_name = re.split(r'[><=]', package_spec)[0]

                try:
                    importlib.import_module(pkg_name)
                except ImportError:
                    logger.info(f"Installing missing package: {package_spec}")
                    subprocess.check_call([sys.executable, '-m', 'pip', 'install', package_spec])

            return func(*args, **kwargs)
        return wrapper
    return decorator
