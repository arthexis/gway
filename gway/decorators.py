import subprocess
import functools
import importlib
import functools
import logging
import sys
import re

logger = logging.getLogger(__name__)


def tag(**new_tags):
    def decorator(func):
        # Find the original function if wrapped
        original_func = func
        while hasattr(original_func, '__wrapped__'):
            original_func = original_func.__wrapped__

        # Merge with any existing tags
        existing_tags = getattr(original_func, 'tags', {})
        merged_tags = {**existing_tags, **new_tags}

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper.tags = merged_tags
        return wrapper
    return decorator


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


requires = tag(decorator=True)(requires)
tag = tag(decorator=True)(tag)


__all__ = ("requires", "tag",)
