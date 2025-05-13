# This is a collection of functions which I consider to be the
# collective public interface of GWAY. One of this should be the
# right entry-point depending on what channel you're comming from.

from .gateway import Gateway, gw
from .command import cli_main, process_commands, load_batch
from .decorators import requires
from .sigils import Sigil, Resolver
from .structs import Results
from .logging import setup_logging
from .environs import load_env
