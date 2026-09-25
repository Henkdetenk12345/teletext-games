import random

HIDDEN = "hidden"
REVEALED = "revealed"
FLAGGED = "flagged"


class Cell:
    def __init__(self):
        self.state = HIDDEN
        self.mine = False
        self.value = 0


class Board:
    def __init__(self, width, height, mines):
        self.width = width
        self.height = height
        self.mine_count = mines
        self.status = "playing"
        self.cells = [[Cell() for _ in range(width)] for _ in range(height)]
        self._place_mines()
        self._compute_values()

    def _place_mines(self):
        positions = [(x, y) for y in range(self.height) for x in range(self.width)]
        for x, y in random.sample(positions, self.mine_count):
            self.cells[y][x].mine = True

    def _neighbors(self, x, y):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    yield nx, ny

    def _compute_values(self):
        for y in range(self.height):
            for x in range(self.width):
                if self.cells[y][x].mine:
                    continue
                self.cells[y][x].value = sum(
                    1 for nx, ny in self._neighbors(x, y) if self.cells[ny][nx].mine
                )

    def reveal(self, x, y):
        if self.status != "playing":
            return
        cell = self.cells[y][x]
        if cell.state != HIDDEN:
            return
        cell.state = REVEALED
        if cell.mine:
            self.status = "lost"
            self._reveal_all_mines()
            return
        if cell.value == 0:
            for nx, ny in self._neighbors(x, y):
                if self.cells[ny][nx].state == HIDDEN:
                    self.reveal(nx, ny)
        self._check_win()

    def _reveal_all_mines(self):
        for row in self.cells:
            for cell in row:
                if cell.mine:
                    cell.state = REVEALED

    def toggle_flag(self, x, y):
        if self.status != "playing":
            return
        cell = self.cells[y][x]
        if cell.state == HIDDEN:
            cell.state = FLAGGED
        elif cell.state == FLAGGED:
            cell.state = HIDDEN

    def _check_win(self):
        for row in self.cells:
            for cell in row:
                if not cell.mine and cell.state != REVEALED:
                    return
        self.status = "won"

    def unrevealed_safe_count(self):
        total_safe = self.width * self.height - self.mine_count
        revealed_safe = sum(
            1 for row in self.cells for c in row if c.state == REVEALED and not c.mine
        )
        return total_safe - revealed_safe

    def flagged_count(self):
        return sum(1 for row in self.cells for c in row if c.state == FLAGGED)

    def to_dict(self):
        return {
            "width": self.width,
            "height": self.height,
            "status": self.status,
            "mine_count": self.mine_count,
            "flagged_count": self.flagged_count(),
            "board": [
                [
                    {
                        "state": c.state,
                        "value": c.value if c.state == REVEALED and not c.mine else None,
                        "mine": c.mine if self.status != "playing" else None,
                    }
                    for c in row
                ]
                for row in self.cells
            ],
        }
