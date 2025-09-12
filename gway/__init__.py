# This is a collection of functions which I consider to be the
# collective public interface of GWAY. One of this should be the
# right entry-point depending on what channel you're comming from.

from .gateway import Gateway, gw, PREFIXES
from .console import cli_main, process, load_recipe
from .sigils import Sigil, Resolver, Spool, __
from .structs import Results
from .logging import setup_logging
from .envs import load_env

# Expose the standalone ``projects`` package under ``gway.projects`` so
# callers can import project modules via ``gway.projects.<name>``.
import sys
from pathlib import Path

try:  # pragma: no cover - depends on installation layout
    import projects as _projects
except ModuleNotFoundError:  # pragma: no cover - ensure direct repo use works
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.append(str(root))
    import projects as _projects

sys.modules[__name__ + ".projects"] = _projects

