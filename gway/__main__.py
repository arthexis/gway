from pathlib import Path
import shlex
import sys

from .console import cli_main

r"""
  __                                 .___        .__                        .___
_/  |_   ____    _____    ____     __| _/  ____  |  |   ______    ____    __| _/  ____  _______
\   __\ /  _ \  /     \  /  _ \   / __ | _/ __ \ |  |   \____ \  /  _ \  / __ | _/ __ \ \_  __ \
 |  |  (  <_> )|  Y Y  \(  <_> ) / /_/ | \  ___/ |  |__ |  |_> >(  <.> )/ /_/ | \  ___/  |  | \/
 |__|   \____/ |__|_|  / \____/  \____ |  \___  >|____/ |   __/  \____/ \____ |  \___  > |__|
                     \/               \/      \/        |__|                 \/      \/

[ Venimos de la Tribu. ] [ A la Tribu volveremos. ]

-- El siguiente [texto] es un poema que se cuenta a si mismo. --

Python/HTML/CSS/SQL code by Rafael Jesús Guillén Osorio (https://arthexis.com)
Comments, reviews and support by Avon[ ]Ross, Keats, INTERCAL and Aristóteles Palimpsesto, III.
Testing, QA Acceptance and mischief instigation by Dr. A. Lince (and His team.)

"""


def _append_history() -> None:
    """Log executed CLI commands to work/history.txt."""
    try:
        cmd = shlex.join(sys.argv[1:])
        path = Path.cwd() / "work" / "history.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(cmd + "\n")
    except Exception:
        # Logging should never block CLI execution
        pass


if __name__ == "__main__":  # pragma: no cover - handled by invocation
    _append_history()
    cli_main()

