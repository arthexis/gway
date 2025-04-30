import functools
import importlib
import subprocess
import sys
import re


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
                    print(f"[requires] Installing missing package: {package_spec}")
                    subprocess.check_call([sys.executable, '-m', 'pip', 'install', package_spec])

            return func(*args, **kwargs)
        return wrapper
    return decorator
