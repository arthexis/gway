# projects/conway.py

# Conway's Game of Life with board state saved to disk
import os
import random
import html

from gway import gw

BOARD_SIZE = 64
BOARD_PATH = None


def _ensure_board_path():
    global BOARD_PATH
    if not BOARD_PATH:
        BOARD_PATH = gw.resource('data', 'conway.txt', touch=True)

def _new_board(size=BOARD_SIZE, fill=0):
    return [[fill for _ in range(size)] for _ in range(size)]

def _random_board(size=BOARD_SIZE):
    return [[random.choice([0, 1]) for _ in range(size)] for _ in range(size)]

def load_board():
    """Load the board from disk, or create one if missing."""
    _ensure_board_path()
    if not BOARD_PATH.exists():
        board = _random_board()
        save_board(board)
        return board
    with open(BOARD_PATH, "r", encoding="utf-8") as f:
        lines = f.read().strip().splitlines()
    try:
        return [[int(cell) for cell in row.split(",")] for row in lines]
    except Exception:
        # If the board file is corrupted, create a new one
        board = _random_board()
        save_board(board)
        return board

def save_board(board):
    """Save the board to disk as CSV rows."""
    _ensure_board_path()
    with open(BOARD_PATH, "w", encoding="utf-8") as f:
        for row in board:
            f.write(",".join(str(cell) for cell in row) + "\n")

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

# TODO: Fix Failed to parse board! on initial load only

def view_board(*args, action=None, board=None, **kwargs):
    """
    Render the Conway's Game of Life UI.
    - action: new, random, step, clear, toggle
    - board: CSV text (flattened)
    """
    msg = ""
    current_board = load_board()

    # Parse incoming board if present (from hidden form field)
    if board:
        if isinstance(board, str):
            try:
                new_board = [
                    [int(cell) for cell in row.split(",")]
                    for row in board.strip().split(";")
                ]
                current_board = new_board
            except Exception:
                msg = "Failed to parse board!"

    if action == "random":
        current_board = _random_board()
    elif action == "clear":
        current_board = _new_board()
    elif action == "new":
        current_board = _new_board()
    elif action == "step":
        current_board = next_generation(current_board)

    save_board(current_board)

    html_board = ""
    for x, row in enumerate(current_board):
        row_html = "".join(
            f'<td class="cell cell-{cell}" data-x="{x}" data-y="{y}"></td>'
            for y, cell in enumerate(row)
        )
        html_board += f"<tr>{row_html}</tr>"

    # Flatten board for form POST
    flat_board = ";".join(",".join(str(cell) for cell in row) for row in current_board)

    # Responsive CSS (supports light/dark backgrounds)
    css = """
    <style>
    :root {
      --cell-off-light: #fafafa;
      --cell-on-light: #222;
      --cell-border-light: #aaa;
      --cell-off-dark: #181818;
      --cell-on-dark: #fafafa;
      --cell-border-dark: #444;
    }
    @media (prefers-color-scheme: dark) {
      .game-board td.cell-0 { background: var(--cell-off-dark); border: 1px solid var(--cell-border-dark); }
      .game-board td.cell-1 { background: var(--cell-on-dark); border: 1px solid var(--cell-border-dark); }
    }
    @media (prefers-color-scheme: light), (prefers-color-scheme: no-preference) {
      .game-board td.cell-0 { background: var(--cell-off-light); border: 1px solid var(--cell-border-light); }
      .game-board td.cell-1 { background: var(--cell-on-light); border: 1px solid var(--cell-border-light); }
    }
    .game-board { border-collapse: collapse; margin-top: 1em;}
    .game-board td { width: 18px; height: 18px; cursor: pointer; transition: background 0.1s;}
    .game-board td { box-sizing: border-box; }
    @media (max-width: 700px) {
      .game-board td { width: 10px; height: 10px;}
    }
    </style>
    """

    # Basic HTML UI with JS for cell toggle
    return f"""
    {css}
    <h1>Conway's Game of Life</h1>
    <div>
        <form id="lifeform" method="post">
            <input type="hidden" name="board" id="boarddata" value="{html.escape(flat_board)}" />
            <button type="submit" name="action" value="step">Step</button>
            <button type="submit" name="action" value="random">Random</button>
            <button type="submit" name="action" value="clear">Clear</button>
        </form>
        <p>{html.escape(msg)}</p>
        <table id="gameboard" class="game-board">{html_board}</table>
    </div>
    <script>
    // Allow clicking cells to toggle state, send to backend
    document.querySelectorAll('.cell').forEach(cell => {{
        cell.onclick = function() {{
            const x = +this.getAttribute('data-x');
            const y = +this.getAttribute('data-y');
            const rows = Array.from(document.querySelectorAll('.game-board tr')).map(
                tr => Array.from(tr.querySelectorAll('.cell')).map(td => td.classList.contains('cell-1') ? 1 : 0)
            );
            rows[x][y] = rows[x][y] ? 0 : 1;
            const flat = rows.map(r => r.join(',')).join(';');
            document.getElementById('boarddata').value = flat;
            document.getElementById('lifeform').submit();
        }};
    }});
    </script>
    """

