from minesweeper import HIDDEN, REVEALED, FLAGGED

# Confirmed from start_veld.tti / 1.tti hex dumps:
#   hidden cell   = 0x12 (mosaic green) + '/'
#   revealed '1'  = 0x03 (alpha yellow) + '1'
# Everything else below this line is a placeholder guess and should be
# checked against the real MINEFINDER generator / a live receiver.
CELL_HIDDEN = bytes([0x12]) + b"/"
CELL_FLAGGED = bytes([0x03]) + b"F"
CELL_MINE = bytes([0x01]) + b"*"
CELL_REVEALED = {
    0: bytes([0x07]) + b" ",
    1: bytes([0x03]) + b"1",
    2: bytes([0x02]) + b"2",
    3: bytes([0x01]) + b"3",
    4: bytes([0x04]) + b"4",
    5: bytes([0x05]) + b"5",
    6: bytes([0x06]) + b"6",
    7: bytes([0x07]) + b"7",
    8: bytes([0x07]) + b"8",
}

STATIC_ROWS = {
    0: b"        832\x07RTL 4    \x07Zo 20 Apr\x0715:17:41",
    1: b"\x17775#; jcj{jkkjsjs      \x04\x1d\x07Score :    0 ",
    2: b"\x11%%%(! *.******,(.      \x04\x1d\x07Rang  :  --- ",
    4: b"\x04\x1d\x07 \x07\x071\x071\x071\x071\x071\x071\x071\x071\x071\x071\x072\x072\x072         ",
    5: b"\x04\x1d\x07  \x070\x071\x072\x073\x074\x075\x076\x077\x078\x079\x070\x071\x072         ",
    19: b"\x14\x1d\x070-scores 7-help                      ",
    20: b"\x14\x1d\x07speel mee via bmn-online.nl          ",
    21: b"\x14\x1d\x07*0#-verlaat minefinder               ",
    22: b" " * 40,
    23: b" " * 40,
}

ROW_LABELS = {
    6: b"nog te",
    7: b"onder-",
    8: b"zoeken",
    9: b"velden",
    13: b"aantal",
    14: b"gemar-",
    15: b"keerde",
    16: b"mijnen",
}


def _mine_row(mines):
    return (
        bytes([0x14])
        + b",,,,,"
        + bytes([0x03])
        + b"MINEFINDER"
        + bytes([0x14])
        + b",,,,,,,"
        + bytes([0x1D, 0x07])
        + f"Mijnen:   {mines:>2} ".encode("ascii")
    )


def _cell_bytes(cell):
    if cell["state"] == HIDDEN:
        return CELL_HIDDEN
    if cell["state"] == FLAGGED:
        return CELL_FLAGGED
    if cell["mine"]:
        return CELL_MINE
    return CELL_REVEALED.get(cell["value"] or 0, CELL_REVEALED[0])


def render_dynamic_rows(board):
    state = board.to_dict()
    rows = {3: _mine_row(state["mine_count"])}
    remaining = board.unrevealed_safe_count()
    flagged = state["flagged_count"]
    for i, row_cells in enumerate(state["board"]):
        row_number = 6 + i
        label = f"{30 + i:>2}".encode("ascii")
        grid = b"".join(_cell_bytes(c) for c in row_cells)
        border = bytes([0x14])
        if row_number == 10:
            tail = bytes([0x01]) + f" {remaining:>3}  ".encode("ascii")
        elif row_number == 17:
            tail = bytes([0x01]) + f" {flagged:>3}  ".encode("ascii")
        elif row_number in ROW_LABELS:
            tail = bytes([0x07]) + ROW_LABELS[row_number]
        else:
            tail = b" " * 7
        row = b" " + label + border + b"j" + grid + border + b"5" + tail
        assert len(row) == 40, f"row {row_number} is {len(row)} bytes, expected 40"
        rows[row_number] = row
    return rows


def render_full_page(board):
    rows = dict(STATIC_ROWS)
    rows.update(render_dynamic_rows(board))
    return rows
