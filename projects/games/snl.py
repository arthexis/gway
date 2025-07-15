# file: projects/games/snl.py
"""Simple shared Massive Snake game (multiplayer Snakes and Ladders)."""

import json
import random
from gway import gw

BOARD_FILE = gw.resource("work", "shared", "games", "massive_snake.json", touch=True)
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
        and getattr(gw.web.app, "is_setup", lambda x: False)("web.cookies")
        and gw.web.cookies.accepted()
    )


def _get_player_id():
    return gw.web.cookies.get("msnake_id") if _use_cookies() else None


def _set_player_id(pid: str):
    if _use_cookies():
        gw.web.cookies.set("msnake_id", pid, path="/", max_age=30 * 24 * 3600)


def _get_ascensions() -> int:
    if not _use_cookies():
        return 0
    try:
        return int(gw.web.cookies.get("msnake_asc") or "0")
    except Exception:
        return 0


def _set_ascensions(val: int):
    if _use_cookies():
        gw.web.cookies.set("msnake_asc", str(val), path="/", max_age=365 * 24 * 3600)


def _add_player(board, name: str, color: str) -> str:
    pid = str(random.randint(100000, 999999))
    board["players"][pid] = {"name": name, "color": color, "pos": 0}
    return pid


def _apply_move(pos: int, roll: int) -> tuple[int, str | None]:
    """Apply a dice roll and return the new position and event."""
    pos += roll
    if pos > BOARD_SIZE:
        pos = BOARD_SIZE - (pos - BOARD_SIZE)
    event = None
    if pos in SNAKES:
        pos = SNAKES[pos]
        event = "snake"
    elif pos in LADDERS:
        pos = LADDERS[pos]
        event = "ladder"
    return max(0, min(pos, BOARD_SIZE)), event


def _board_html(board: dict) -> str:
    """Return an abstract HTML board grid."""
    # collect players per position for quick lookup
    players_at = {}
    for info in board.get("players", {}).values():
        players_at.setdefault(info.get("pos", 0), []).append(info)

    rows = []
    for r in range(10):
        start = BOARD_SIZE - r * 10
        nums = range(start, start - 10, -1) if r % 2 == 0 else range(start - 9, start + 1)
        cells = []
        for n in nums:
            classes = []
            if n in SNAKES:
                classes.append("snake")
            if n in LADDERS:
                classes.append("ladder")
            marks = "".join(
                f'<span class="player" style="color:{p.get("color", "#000")}">&#9679;</span>'
                for p in players_at.get(n, [])
            )
            num = f'<div class="num">{n}</div>'
            cells.append(f'<td class="{" ".join(classes)}">{num}{marks}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return '<table class="snake-board">' + "".join(rows) + "</table>"


def view_massive_snake(*, action=None, name=None, color=None):
    """Main Massive Snake view."""
    board = load_board()
    pid = _get_player_id()
    asc = _get_ascensions()
    ready_to_ascend = False

    if not pid and name and color:
        pid = _add_player(board, name, color)
        save_board(board)
        _set_player_id(pid)

    message = ""
    roll_msg = ""
    disable_roll = False
    if action == "ascend" and pid and board["players"].get(pid, {}).get("pos") >= BOARD_SIZE:
        asc += 1
        _set_ascensions(asc)
        board["players"][pid]["pos"] = 0
        save_board(board)
        message = "Ascended!"
        disable_roll = True
    elif action == "roll":
        roll = random.randint(1, 6)
        board["last_roll"] = roll
        event = None
        for pid_, pdata in board["players"].items():
            new_pos, ev = _apply_move(pdata.get("pos", 0), roll)
            pdata["pos"] = new_pos
            if pid_ == pid:
                event = ev
        save_board(board)
        message = f"Rolled {roll}!"
        if event == "ladder":
            message += " You went up a ladder!"
            disable_roll = True
        elif event == "snake":
            message += " You fell down a snake!"
            disable_roll = True
        if pid and board["players"].get(pid, {}).get("pos", 0) >= BOARD_SIZE:
            ready_to_ascend = True
            message += " Ready to ascend!"
        roll_msg = message
        message = ""

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
    ascend_button = ""
    if pid:
        player_pos = board["players"].get(pid, {}).get("pos", 0)
        ready_to_ascend = ready_to_ascend or player_pos >= BOARD_SIZE
        if player_pos < BOARD_SIZE:
            roll_button = (
                "<form method='post' class='snake-roll'>"
                "<button class='snake-button roll-button' type='submit' name='action' value='roll'>Roll Dice</button>"
                f"<span class='roll-msg'>{gw.web.nav.html_escape(roll_msg)}</span>"
                "</form>"
            )
        if player_pos >= BOARD_SIZE:
            ascend_button = (
                "<form method='post' class='snake-ascend' style='display:inline-block'>"
                "<button class='snake-button ascend-button' type='submit' name='action' value='ascend'>Ascend</button>"
                "<span id='ascend-msg' class='ascend-msg'></span>"
                "</form>"
            )

    script_parts = []
    if ready_to_ascend and pid:
        script_parts.append("<script>window.msnakeReadyToAscend=true;</script>")
    if disable_roll:
        script_parts.append("<script>window.msnakeDisableRoll=true;</script>")
    script = ''.join(script_parts)

    html = [
        '<link rel="stylesheet" href="/static/games/massive_snake/board.css">',
        '<script src="/static/games/massive_snake/massive_snake.js"></script>',
        "<h1 id='msnake-title' class='snake-title'>Massive Snake</h1>",
        script,
        "<p><em>A Massively Multiplayer Game of Snakes and Ladders.</em></p>",
        join_form,
        f"<p>{message}</p>" if message else "",
        f"<p>Ascensions: {asc}</p>" if pid else "",
        roll_button,
        ascend_button,
        "<table><tr><th>Player</th><th>Position</th></tr>",
        "".join(rows),
        "</table>",
        _board_html(board),
    ]
    return "\n".join(html)
