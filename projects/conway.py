# file: projects/conway.py

import os
import random
import html
from datetime import datetime

from gway import gw
from bottle import response, redirect

BOARD_SIZE = 54
BOARD_FILE = gw.resource("work", "conway.txt", touch=True)

def _new_board(size=BOARD_SIZE, fill=0):
    return [[fill for _ in range(size)] for _ in range(size)]

def _random_board(size=BOARD_SIZE):
    return [[random.choice([0, 1]) for _ in range(size)] for _ in range(size)]

def _serialize_board(board):
    return "\n".join(",".join(str(cell) for cell in row) for row in board)

def _deserialize_board(s):
    return [[int(cell) for cell in row.split(",")] for row in s.strip().splitlines()]

def load_board():
    """Load the board from disk, or create one if missing."""
    if not os.path.exists(BOARD_FILE):
        board = _random_board()
        save_board(board)
        return board
    with open(BOARD_FILE, "r", encoding="utf-8") as f:
        try:
            return _deserialize_board(f.read())
        except Exception:
            board = _random_board()
            save_board(board)
            return board

def save_board(board):
    """Save the board to disk as CSV rows."""
    with open(BOARD_FILE, "w", encoding="utf-8") as f:
        f.write(_serialize_board(board))

def is_board_empty(board):
    return all(cell == 0 for row in board for cell in row)

def is_board_full(board):
    return all(cell == 1 for row in board for cell in row)

def flip_board(board):
    return [[1 - cell for cell in row] for row in board]

def next_generation(board):
    size = len(board)
    def neighbors(r, c):
        return sum(
            board[(r+dr)%size][(c+dc)%size]
            for dr in (-1,0,1) for dc in (-1,0,1)
            if (dr,dc)!=(0,0)
        )
    return [
        [1 if (cell and 2<=neighbors(r,c)<=3) or (not cell and neighbors(r,c)==3) else 0
         for c,cell in enumerate(row)]
        for r,row in enumerate(board)
    ]

def view_download_board():
    """Download the current board as a text file."""
    board = load_board()
    text = _serialize_board(board)
    response.content_type = 'text/plain'
    response.headers['Content-Disposition'] = 'attachment; filename="conway.txt"'
    return text

def view_game_of_life(
    *args,
    action=None,
    board=None,
    toggle_x=None,
    toggle_y=None,
    **kwargs
):
    # 1. Load the current board
    msg = ""
    current_board = load_board()

    # 2. Handle form board (from hidden input)
    if board:
        try:
            new_board = [
                [int(cell) for cell in row.split(",")]
                for row in board.strip().split(";")
            ]
            current_board = new_board
        except Exception:
            msg = "Failed to parse board!"

    # 3. Action handlers
    if action == "random":
        current_board = _random_board()
    elif action == "clear":
        current_board = _new_board()
    elif action == "step":
        current_board = next_generation(current_board)
    elif action == "toggle":
        x = int(toggle_x) if toggle_x is not None else -1
        y = int(toggle_y) if toggle_y is not None else -1
        if 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE:
            current_board[x][y] = 0 if current_board[x][y] else 1
        save_board(current_board)
        return redirect("/conway/game-of-life")  # POST-redirect-GET

    # 4. Always save board for step/random/clear (toggle already saved above)
    if action in ("step", "random", "clear"):
        save_board(current_board)

    # 5. Prepare HTML board
    html_board = ""
    for x, row in enumerate(current_board):
        row_html = "".join(
            f'<td class="cell cell-{cell}" data-x="{x}" data-y="{y}"></td>'
            for y, cell in enumerate(row)
        )
        html_board += f"<tr>{row_html}</tr>"

    flat_board = ";".join(",".join(str(cell) for cell in row) for row in current_board)

    # 6. Get last modified date of board file
    last_mod = None
    if os.path.exists(BOARD_FILE):
        last_mod = datetime.fromtimestamp(os.path.getmtime(BOARD_FILE)).strftime("%Y-%m-%d %H:%M:%S")

    ICONS = {
        "step": '<svg viewBox="0 0 20 20"><polyline points="5,3 15,10 5,17" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
        "random": '<svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="8" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="10" cy="10" r="3" fill="currentColor"/></svg>',
        "clear": '<svg viewBox="0 0 20 20"><rect x="4" y="4" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"/><line x1="6" y1="6" x2="14" y2="14" stroke="currentColor" stroke-width="2"/><line x1="14" y1="6" x2="6" y2="14" stroke="currentColor" stroke-width="2"/></svg>',
        "download": '<svg viewBox="0 0 20 20"><path d="M10 3v10m0 0l-4-4m4 4l4-4M3 17h14" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
    }

    return f"""
    <h1>Conway's Game of Life</h1>
    <div>
        <form id="lifeform" method="post" class="game-actions" autocomplete="off" style="margin-bottom:8px;">
            <input type="hidden" name="board" id="boarddata" value="{html.escape(flat_board)}" />
            <button type="submit" name="action" value="step">{ICONS['step']} Step Forward</button>
            <button type="submit" name="action" value="random">{ICONS['random']} Random</button>
            <button type="submit" name="action" value="clear">{ICONS['clear']} Clear</button>
            <a href="/web/conway/download" download class="button">{ICONS['download']} Download</a>
        </form>
        <p style="color:#aa2222">{html.escape(msg)}</p>
        <table id="gameboard" class="game-board">{html_board}</table>
        <div style="margin-top:0.8em;color:#888;font-size:0.96em">
            Last updated: {last_mod or "Never"}
        </div>
    </div>
    """
