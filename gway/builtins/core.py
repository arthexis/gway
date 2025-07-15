import code

__all__ = [
    "hello_world",
    "abort",
    "envs",
    "version",
    "shell",
]

def hello_world(name: str = "World", *, greeting: str = "Hello", **kwargs):
    """Smoke test function."""
    from gway import gw
    version = gw.version()
    message = f"{greeting.title()}, {name.title()}!"
    if hasattr(gw, "hello_world"):
        if not gw.silent:
            print(message)
        else:
            print(f"{gw.silent=}")
    else:
        print("Greeting protocol not found ((serious smoke)).")
    return {
        "greeting": greeting,
        "name": name,
        "message": message,
        "version": version,
    }


def abort(message: str, *, exit_code: int = 13) -> int:
    from gway import gw
    """Abort with error message."""
    gw.critical(message)
    print(f"Halting: {message}")
    raise SystemExit(exit_code)


def envs(filter: str | None = None) -> dict:
    """Return environment variables, optionally filtered."""
    import os

    if filter:
        filter = filter.upper()
        return {k: v for k, v in os.environ.items() if filter in k}
    return os.environ.copy()


def version(check: str | None = None) -> str:
    """Return the version of the package."""
    from gway import gw
    import os

    def parse_version(vstr: str):
        parts = vstr.strip().split(".")
        if len(parts) == 1:
            parts = (parts[0], "0", "0")
        elif len(parts) == 2:
            parts = (parts[0], parts[1], "0")
        if len(parts) > 3:
            raise ValueError(
                f"Invalid version format: '{vstr}', expected 'major.minor.patch'"
            )
        return tuple(int(part) for part in parts)

    version_path = gw.resource("VERSION")
    if os.path.exists(version_path):
        with open(version_path, "r") as version_file:
            current_version = version_file.read().strip()
        if check:
            current_tuple = parse_version(current_version)
            required_tuple = parse_version(check)
            if current_tuple < required_tuple:
                raise AssertionError(
                    f"Required version >= {check}, found {current_version}"
                )
        return current_version
    gw.critical("VERSION file not found.")
    return "unknown"


def shell():
    """Launch an interactive Python shell with gw preloaded."""
    from gway import gw
    from gway import __

    local_vars = {"gw": gw, "__": __}
    banner = "GWAY interactive shell.\nfrom gway import gw  # Python 3.13 compatible"
    code.interact(banner=banner, local=local_vars)


