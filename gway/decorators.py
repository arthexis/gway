import subprocess
import functools
import importlib
import logging
import sys
import re
import os

logger = logging.getLogger(__name__)

_requirement_cache = set()

def requires(*packages):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from gway import Gateway
            gway = Gateway()

            temp_req_file = gway.resource("temp", "requirements.txt")
            existing_reqs = set()

            if os.path.exists(temp_req_file):
                with open(temp_req_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            existing_reqs.add(line)

            for package_spec in packages:
                if package_spec in _requirement_cache:
                    continue

                # Extract base package name for import (handles things like qrcode[pil], numpy>=1.21, etc.)
                pkg_name = re.split(r'[><=\[]', package_spec)[0]

                try:
                    importlib.import_module(pkg_name)
                except ImportError:
                    logger.info(f"Installing missing package: {package_spec}")
                    subprocess.check_call([sys.executable, '-m', 'pip', 'install', package_spec])
                    try:
                        importlib.import_module(pkg_name)
                    except ImportError:
                        gway.abort(f"Unable to install and import {package_spec}")

                    if package_spec not in existing_reqs:
                        with open(temp_req_file, "a") as f:
                            f.write(package_spec + "\n")
                        existing_reqs.add(package_spec)

                _requirement_cache.add(package_spec)

            return func(*args, **kwargs)
        return wrapper
    return decorator


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


requires = tag(decorator=True)(requires)
tag = tag(decorator=True)(tag)


__all__ = ("requires", "tag",)
