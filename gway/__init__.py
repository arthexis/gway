# This is a collection of functions which I consider to be the
# collective public interface of GWAY. One of this should be the
# right entry-point depending on what channel you're comming from.

from .gateway import Gateway, gw, PREFIXES
from .console import cli_main, process, load_recipe
from .sigils import Sigil, Resolver, Spool, __
from .structs import Results
from .logging import setup_logging
from ._env_bindings import resolve_env_bindings

_ENV_BINDINGS = resolve_env_bindings()
load_env = _ENV_BINDINGS.load_env

