import os
import logging


logger = logging.getLogger(__name__)


def get_base_client():
    """Get the default client name based on logged in username."""
    try:
        import getpass
        username = getpass.getuser()
        return username if username else "guest"
    except Exception:
        return "guest"
    

def get_base_server():
    """Get the default server name based on machine hostname."""
    try:
        import socket
        hostname = socket.gethostname()
        return hostname if hostname else "localhost"
    except Exception:
        return "localhost"
    

def parse_env_file(env_file):
    env_vars = {}
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()
    return env_vars


def load_env(env_type: str, name: str, env_root: str):
    """
    Load environment variables from envs/{clients|servers}/{name}.env
    If the file doesn't exist, create an empty one and log a warning.
    Ensures the .env filename is always lowercase.
    Supports BASE_ENV which can be defined in the main env file,
    but base env vars will not override the primary env's values.
    """
    assert env_type in ("clients", "servers"), "env_type must be 'clients' or 'servers'"
    env_dir = os.path.join(env_root, env_type)
    os.makedirs(env_dir, exist_ok=True)

    env_file = os.path.join(env_dir, f"{name.lower()}.env")

    if not os.path.isfile(env_file):
        open(env_file, "a").close()
        logger.warning(f"{env_type.capitalize()} env file '{env_file}' not found. Created an empty one.")
        return

    # Load primary env file
    primary_env = parse_env_file(env_file)

    # Check for BASE_ENV
    base_env_name = primary_env.get("BASE_ENV")
    if base_env_name:
        base_env_file = os.path.join(env_dir, f"{base_env_name.lower()}.env")
        if os.path.isfile(base_env_file):
            base_env = parse_env_file(base_env_file)
            for key, value in base_env.items():
                if key not in primary_env:
                    os.environ[key] = value
                    logger.debug(f"Loaded base env var: {key}={value}")
        else:
            logger.warning(f"BASE_ENV '{base_env_name}' referenced but not found at '{base_env_file}'.")

    # Load primary env variables (override base if needed)
    for key, value in primary_env.items():
        os.environ[key] = value
        logger.debug(f"Loaded env var: {key}={value}")
