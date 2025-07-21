# file: projects/games/four_in_a_row.py
"""Prototype Tetrad (Four In A Row) game for a single player versus the computer."""

import random
import html

ROWS = 6
COLS = 7


def _empty_board():
    return [[0 for _ in range(COLS)] for _ in range(ROWS)]


def _parse_board(data: str | None):
    if not data or len(data) != ROWS * COLS:
        return _empty_board()
    cells = [int(c) for c in data]
    return [cells[i * COLS : (i + 1) * COLS] for i in range(ROWS)]


def _serialize_board(board) -> str:
    return "".join(str(cell) for row in board for cell in row)


def _drop(board, col, player):
    for r in range(ROWS - 1, -1, -1):
        if board[r][col] == 0:
            board[r][col] = player
            return True
    return False


def _check_win(board, player):
    # horizontal
    for r in range(ROWS):
        for c in range(COLS - 3):
            if all(board[r][c + i] == player for i in range(4)):
                return True
    # vertical
    for c in range(COLS):
        for r in range(ROWS - 3):
            if all(board[r + i][c] == player for i in range(4)):
                return True
    # diag down-right
    for r in range(ROWS - 3):
        for c in range(COLS - 3):
            if all(board[r + i][c + i] == player for i in range(4)):
                return True
    # diag up-right
    for r in range(3, ROWS):
        for c in range(COLS - 3):
            if all(board[r - i][c + i] == player for i in range(4)):
                return True
    return False


def view_four_in_a_row(*, board=None, col=None, reset=None):
    board_state = _parse_board(board)
    message = ""
    game_over = False

    if reset:
        board_state = _empty_board()
    elif col is not None:
        col = int(col)
        if _drop(board_state, col, 1):
            if _check_win(board_state, 1):
                message = "You win!"
                game_over = True
            elif all(board_state[0][c] != 0 for c in range(COLS)):
                message = "Draw!"
                game_over = True
            else:
                # computer move
                choices = [c for c in range(COLS) if board_state[0][c] == 0]
                if choices:
                    block_col = None
                    for c in choices:
                        temp = [row[:] for row in board_state]
                        _drop(temp, c, 1)
                        if _check_win(temp, 1):
                            block_col = c
                            break

                    computer_col = block_col if block_col is not None else random.choice(choices)
                    _drop(board_state, computer_col, 2)
                    if _check_win(board_state, 2):
                        message = "Computer wins!"
                        game_over = True

    board_str = _serialize_board(board_state)
    html_rows = []
    # header with buttons
    header = ["<tr>"]
    for c in range(COLS):
        disabled = (
            " disabled" if game_over or board_state[0][c] != 0 else ""
        )
        header.append(
            f"<th class='fiar-column'><button type='submit' name='col' value='{c}'{disabled}>▼</button></th>"
        )
    header.append("</tr>")
    html_rows.append("".join(header))

    for r in range(ROWS):
        cells = []
        for c in range(COLS):
            cell = board_state[r][c]
            cls = "player1" if cell == 1 else "player2" if cell == 2 else ""
            cells.append(f"<td class='{cls}'></td>")
        html_rows.append("<tr>" + "".join(cells) + "</tr>")

    html_output = [
        '<link rel="stylesheet" href="/static/web/cards.css">',
        '<link rel="stylesheet" href="/static/games/four_in_a_row/four_in_a_row.css">',
        "<h1>Tetrad (Four In A Row)</h1>",
        "<form method='post' class='fiar-form'>",
        f"<input type='hidden' name='board' value='{html.escape(board_str)}'>",
        "<table class='fiar-board'>",
        *html_rows,
        "</table>",
    ]
    if message:
        html_output.append(f"<p>{html.escape(message)}</p>")
    html_output.append(
        "<p><button type='submit' name='reset' value='1'>New Game</button></p>"
    )
    html_output.append("</form>")
    return "\n".join(html_output)
