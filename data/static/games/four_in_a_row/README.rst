Tetrad Cookie Format
====================

The board consists of seven columns and six rows (42 cells). Each cell can
be in one of four states:

``0`` – Open slot ready for a move
``1`` – Player disc
``2`` – Computer disc
``3`` – Unavailable (future moves not allowed yet)

Two adjacent cells are stored in one byte using the upper and lower nibble.
A complete board uses 21 bytes which we encode with Base64 to keep the cookie
value short and URL‐safe. Orientation is row major, so the first nibble holds
``board[0][0]`` and the second nibble ``board[0][1]`` and so on. Unused bits in
the final byte are zeroed.

Pseudo code::

    def encode_board(board):
        nibbles = [cell & 0xF for row in board for cell in row]
        buf = bytearray()
        for i in range(0, len(nibbles), 2):
            hi = nibbles[i] << 4
            lo = nibbles[i + 1] if i + 1 < len(nibbles) else 0
            buf.append(hi | lo)
        return base64.b64encode(buf).decode()

    def decode_board(value):
        data = base64.b64decode(value)
        cells = []
        for b in data:
            cells.append(b >> 4)
            cells.append(b & 0xF)
        cells = cells[:42]
        return [cells[i*7:(i+1)*7] for i in range(6)]

Use the cookie key ``fiar_board`` (expiry e.g. two weeks). When loading the
page, decode the cookie value to restore the board. Player moves are triggered
by clicking a column with an open slot. After the player's drop, the computer
first checks if that move created a threat of an immediate win on the next
turn. If so it blocks that column, otherwise it selects a random legal column
and stores the updated board back in the cookie.
