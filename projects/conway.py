# projects/conway.py

import os
import random
import html
import glob

from gway import gw
from bottle import response, redirect

BOARD_SIZE = 54
BOARD_BASENAME = "conway"
BOARD_DIR = gw.resource("work")
BOARD_PATTERN = os.path.join(BOARD_DIR, f"{BOARD_BASENAME}_*.txt")

def _board_path(step):
    return os.path.join(BOARD_DIR, f"{BOARD_BASENAME}_{step}.txt")

def _find_latest_board_file():
    files = glob.glob(BOARD_PATTERN)
    max_step = 0
    for f in files:
        try:
            s = int(os.path.splitext(os.path.basename(f))[0].split("_")[1])
            if s > max_step:
                max_step = s
        except Exception:
            continue
    return _board_path(max_step), max_step

def _delete_old_boards(except_step):
    for f in glob.glob(BOARD_PATTERN):
        try:
            s = int(os.path.splitext(os.path.basename(f))[0].split("_")[1])
            if s != except_step:
                os.remove(f)
        except Exception:
            continue

def _new_board(size=BOARD_SIZE, fill=0):
    return [[fill for _ in range(size)] for _ in range(size)]

def _random_board(size=BOARD_SIZE):
    return [[random.choice([0, 1]) for _ in range(size)] for _ in range(size)]

def _serialize_board(board):
    return "\n".join(",".join(str(cell) for cell in row) for row in board)

def _deserialize_board(s):
    return [[int(cell) for cell in row.split(",")] for row in s.strip().splitlines()]

def load_board():
    """Returns (board, step)"""
    path, step = _find_latest_board_file()
    if not os.path.exists(path):
        board = _random_board()
        step = 0
        save_board(board, step)
        return board, step
    with open(path, "r", encoding="utf-8") as f:
        try:
            board = _deserialize_board(f.read())
            return board, step
        except Exception:
            board = _random_board()
            step = 0
            save_board(board, step)
            return board, step

def save_board(board, step):
    """Save board to disk as CSV, naming file with step."""
    path = _board_path(step)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_serialize_board(board))
    _delete_old_boards(except_step=step)

def is_board_empty(board):
    return all(cell == 0 for row in board for cell in row)

def is_board_full(board):
    return all(cell == 1 for row in board for cell in row)

def flip_board(board):
    return [[1 - cell for cell in row] for row in board]

def next_generation(board):
    """Compute the next Game of Life generation."""
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

# --- Download view ---
def view_download_board():
    """Download the current board as a text file."""
    board, step = load_board()
    text = _serialize_board(board)
    response.content_type = 'text/plain'
    response.headers['Content-Disposition'] = f'attachment; filename="conway_{step}.txt"'
    return text

def view_game_of_life(
    *args,
    action=None,
    board=None,
    auto=False,
    toggle_x=None,
    toggle_y=None,
    **kwargs
):
    # Accept both bool and str for auto
    if isinstance(auto, str):
        auto = auto.lower() in ("1", "true", "yes", "on")

    # If we get POSTed board (from cell click), parse from `;`
    if board:
        try:
            board_data = [[int(cell) for cell in row.split(",")] for row in board.strip().split(";")]
            step = None
        except Exception:
            board_data, step = load_board()
    else:
        board_data, step = load_board()

    if step is None:
        step = 0

    if action in ("random", "new"):
        board_data = _random_board() if action == "random" else _new_board()
        step = 0
        save_board(board_data, step)
    elif action == "clear":
        if is_board_empty(board_data):
            board_data = flip_board(board_data)
        else:
            board_data = _new_board()
        step = 0
        save_board(board_data, step)
    elif action == "step":
        board_data = next_generation(board_data)
        step += 1
        save_board(board_data, step)
    elif action == "toggle":
        x = int(toggle_x) if toggle_x is not None else -1
        y = int(toggle_y) if toggle_y is not None else -1
        if 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE:
            board_data[x][y] = 0 if board_data[x][y] else 1
        if auto:
            board_data = next_generation(board_data)
            step += 1
        save_board(board_data, step)
        return redirect(f"/conway/game-of-life?auto={'1' if auto else '0'}")

    # Render HTML board
    html_board = ""
    for x, row in enumerate(board_data):
        row_html = "".join(
            f'<td class="cell cell-{cell}" data-x="{x}" data-y="{y}"></td>'
            for y, cell in enumerate(row)
        )
        html_board += f"<tr>{row_html}</tr>"

    flat_board = ";".join(",".join(str(cell) for cell in row) for row in board_data)

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
            <button type="submit" name="action" value="step">{ICONS['step']} Step [{step:04}]</button>
            <label class="auto-label">
                <input type="checkbox" name="auto" value="1" id="autostep" {"checked" if auto else ""} onchange="document.getElementById('lifeform').submit();" />
                Auto
            </label>
            <button type="submit" name="action" value="random">{ICONS['random']} Random</button>
            <button type="submit" name="action" value="clear">{ICONS['clear']} Clear</button>
            <a href="/web/conway/download" download class="button">{ICONS['download']} Download</a>
        </form>
        <table id="gameboard" class="game-board">{html_board}</table>
    </div>
    """
