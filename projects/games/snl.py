# file: projects/games/snl.py
"""Simple shared Snakes and Ladders game."""

import json
import random
from gway import gw

BOARD_FILE = gw.resource("work", "shared", "games", "snl.json", touch=True)
BOARD_SIZE = 100

# Basic snakes and ladders layout
SNAKES = {16: 6, 48: 26, 49: 11, 56: 53, 62: 19, 64: 60, 93: 73, 95: 75, 98: 78}
LADDERS = {1: 38, 4: 14, 9: 31, 21: 42, 28: 84, 36: 44, 51: 67, 71: 91, 80: 100}


def load_board():
    """Load the shared board from disk or initialize a new one."""
    if BOARD_FILE.exists() and BOARD_FILE.stat().st_size > 0:
        try:
            with open(BOARD_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            gw.warn(f"Failed loading board: {e}")
    board = {"players": {}, "last_roll": 0}
    save_board(board)
    return board


def save_board(board):
    with open(BOARD_FILE, "w", encoding="utf-8") as f:
        json.dump(board, f)


def _use_cookies():
    return (
        hasattr(gw.web, "app")
        and hasattr(gw.web, "cookies")
        and getattr(gw.web.app, "is_make", lambda x: False)("web.cookies")
        and gw.web.cookies.accepted()
    )


def _get_player_id():
    return gw.web.cookies.get("snl_id") if _use_cookies() else None


def _set_player_id(pid: str):
    if _use_cookies():
        gw.web.cookies.set("snl_id", pid, path="/", max_age=30 * 24 * 3600)


def _add_player(board, name: str, color: str) -> str:
    pid = str(random.randint(100000, 999999))
    board["players"][pid] = {"name": name, "color": color, "pos": 0}
    return pid


def _apply_move(pos: int, roll: int) -> int:
    pos += roll
    if pos in SNAKES:
        pos = SNAKES[pos]
    elif pos in LADDERS:
        pos = LADDERS[pos]
    return min(pos, BOARD_SIZE)


def view_snl_board(*, action=None, name=None, color=None):
    """Main Snakes and Ladders view."""
    board = load_board()
    pid = _get_player_id()

    if not pid and name and color:
        pid = _add_player(board, name, color)
        save_board(board)
        _set_player_id(pid)

    message = ""
    if action == "roll":
        roll = random.randint(1, 6)
        board["last_roll"] = roll
        for pdata in board["players"].values():
            pdata["pos"] = _apply_move(pdata.get("pos", 0), roll)
        save_board(board)
        message = f"Rolled {roll}!"

    rows = []
    for pid_, info in board["players"].items():
        style = f" style=\"color:{info.get('color','')}\"" if info.get("color") else ""
        me = " (you)" if pid_ == pid else ""
        name_html = gw.web.nav.html_escape(info.get("name", "Player"))
        rows.append(f"<tr><td{style}>{name_html}{me}</td><td>{info.get('pos',0)}</td></tr>")

    join_form = ""
    if not pid:
        join_form = (
            "<form method='post'>"
            "<input name='name' placeholder='Name' required> "
            "<input name='color' type='color' value='#ff0000' required> "
            "<button type='submit'>Join</button>"
            "</form>"
        )

    roll_button = ""
    if pid:
        roll_button = (
            "<form method='post'>"
            "<button type='submit' name='action' value='roll'>Roll Dice</button>"
            "</form>"
        )

    html = [
        "<h1>Snakes and Ladders</h1>",
        join_form,
        f"<p>{message}</p>" if message else "",
        roll_button,
        "<table><tr><th>Player</th><th>Position</th></tr>",
        "".join(rows),
        "</table>",
    ]
    return "\n".join(html)
