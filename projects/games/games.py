# file: projects/games/games.py
"""Central home view and aliases for all games."""

import importlib.util
from pathlib import Path


def _load(mod_file: str, name: str):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).with_name(mod_file)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    return module


conway = _load("conway.py", "games.conway")
mtg = _load("mtg.py", "games.mtg")
qpig = _load("qpig.py", "games.qpig")
massive_snake = _load("snl.py", "games.massive_snake")
evennia = _load("evennia.py", "games.evennia")

WIKI_ICON = (
    '<svg viewBox="0 0 20 20" width="12" height="12" style="vertical-align:baseline">'
    '<path d="M10 3h7v7h-2V6.414l-9.293 9.293-1.414-1.414L13.586 5H10V3z" fill="currentColor"/>'
    '<path d="M5 5h3V3H3v5h2V5z" fill="currentColor"/></svg>'
)


_DEF = [
    (
        "Conway's Game of Life",
        "game-of-life",
        "A classic cellular automaton that shows how complex patterns arise from simple rules.",
        "https://en.wikipedia.org/wiki/Conway%27s_Game_of_Life",
    ),
    (
        "Lookup Wars",
        "search-games",
        "Look up Magic: The Gathering cards using the Scryfall API.",
        "https://en.wikipedia.org/wiki/Magic:_The_Gathering",
    ),
    (
        "Quantum Piggy Farm",
        "qpig-farm",
        "Prototype incremental game about raising quantum guinea pigs.",
        "https://en.wikipedia.org/wiki/Incremental_game",
    ),
    (
        "Massive Snake",
        "massive-snake",
        "A Massively Multiplayer Game of Snakes and Ladders.",
        "https://en.wikipedia.org/wiki/Snakes_and_Ladders",
    ),
    (
        "Evennia MUD",
        "evennia",
        "Install and control a local Evennia server.",
        "https://www.evennia.com/",
    ),
    (
        "Fantastic Client",
        "fantastic-client",
        "Login to the Evennia server using the web client.",
        "https://www.evennia.com/",
    ),
]


def view_games():
    """Home view listing all available games."""
    html = ["<h1>Games</h1>", "<ul class='games-list'>"]
    for title, route, desc, link in _DEF:
        wiki = f'<a href="{link}" target="_blank" class="wiki">{WIKI_ICON}</a>'
        html.append(
            f"<li><a href='/games/{route}'><b>{title}</b></a><br><span>{desc} {wiki}</span></li>"
        )
    html.append("</ul>")
    return "\n".join(html)


def view_game_of_life(*args, **kwargs):
    return conway.view_game_of_life(*args, **kwargs)


def view_search_games(*args, **kwargs):
    return mtg.view_search_games(*args, **kwargs)


def view_qpig_farm(*args, **kwargs):
    return qpig.view_qpig_farm(*args, **kwargs)


def view_massive_snake(*args, **kwargs):
    return massive_snake.view_massive_snake(*args, **kwargs)


def view_evennia(*args, **kwargs):
    return evennia.view_evennia(*args, **kwargs)


def view_fantastic_client(*args, **kwargs):
    return evennia.view_fantastic_client(*args, **kwargs)

