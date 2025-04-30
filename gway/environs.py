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
    

def load_env(env_type: str, name: str, env_root: str):
    """
    Load environment variables from envs/{clients|servers}/{name}.env
    If the file doesn't exist, create an empty one and log a warning.
    Ensures the .env filename is always lowercase.
    """
    assert env_type in ("clients", "servers"), "env_type must be 'clients' or 'servers'"
    env_dir = os.path.join(env_root, env_type)
    os.makedirs(env_dir, exist_ok=True)  # Create folder structure if needed

    # Ensure the name is lowercase for the filename
    env_file = os.path.join(env_dir, f"{name.lower()}.env")

    if not os.path.isfile(env_file):
        # Create empty .env file
        open(env_file, "a").close()
        logger.warning(f"{env_type.capitalize()} env file '{env_file}' not found. Created an empty one.")
        return

    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue  # Skip comments and empty lines
            if "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()
                logger.debug(f"Loaded env var: {key.strip()}={value.strip()}")