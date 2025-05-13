import subprocess
import functools
import importlib
import sys
import re
import os


_requirement_cache = set()

def requires(*packages):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from gway import gw
            gw.debug(f"Required {packages=}")

            for package_spec in packages:
                if package_spec in _requirement_cache:
                    continue

                # Extract base package name for import (handles things like qrcode[pil], numpy>=1.21, etc.)
                pkg_name = re.split(r'[><=\[]', package_spec)[0]

                try:
                    gw.debug(f"Try import {pkg_name=}")
                    importlib.import_module(pkg_name)
                except ImportError:
                    gw.info(f"Installing missing package: {package_spec}")
                    subprocess.check_call([sys.executable, '-m', 'pip', 'install', package_spec])
                    try:
                        gw.debug(f"Retry import {pkg_name=}")
                        importlib.import_module(pkg_name)
                    except ImportError:
                        gw.abort(f"Unable to install and import {package_spec}")
                                
                    temp_req_file = gw.resource("temp", "requirements.txt")
                    existing_reqs = set()

                    if os.path.exists(temp_req_file):
                        with open(temp_req_file, "r") as f:
                            for line in f:
                                line = line.strip()
                                if line:
                                    existing_reqs.add(line)

                        if package_spec not in existing_reqs:
                            with open(temp_req_file, "a") as f:
                                f.write(package_spec + "\n")
                            existing_reqs.add(package_spec)

                _requirement_cache.add(package_spec)

            return func(*args, **kwargs)
        return wrapper
    return decorator

