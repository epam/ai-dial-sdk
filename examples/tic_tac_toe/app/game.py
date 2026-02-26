from typing import Literal

from pydantic import BaseModel

# 1 for X
# 2 for O
Player = Literal[1, 2]

X_PLAYER: Player = 1
O_PLAYER: Player = 2


def _print_player(player: Player) -> str:
    return "X" if player == X_PLAYER else "O"


class Move(BaseModel):
    row: int
    col: int

    @classmethod
    def from_button_value(cls, move: int) -> "Move":
        return Move(row=(move % 10) - 1, col=(move // 10) - 1)

    def to_button_value(self) -> int:
        return (self.row + 1) + 10 * (self.col + 1)

    def print(self) -> str:
        col = {0: "A", 1: "B", 2: "C"}[self.col]
        row = self.row + 1
        return f"{col}{row}"

    @staticmethod
    def col_lines() -> list[list["Move"]]:
        return [
            [Move(row=row, col=col) for row in range(3)] for col in range(3)
        ]

    @staticmethod
    def row_lines() -> list[list["Move"]]:
        return [
            [Move(row=row, col=col) for col in range(3)] for row in range(3)
        ]

    @staticmethod
    def diag_lines() -> list[list["Move"]]:
        return [
            [Move(row=i, col=i) for i in range(3)],
            [Move(row=i, col=2 - i) for i in range(3)],
        ]


class Board(BaseModel):
    cells: list[list[Player | None]] = [[None] * 3] * 3
    """Current state of the game board"""

    @property
    def x_moves(self) -> int:
        return sum(row.count(X_PLAYER) for row in self.cells)

    @property
    def o_moves(self) -> int:
        return sum(row.count(O_PLAYER) for row in self.cells)

    @property
    def player(self) -> Player:
        """Returns the player who should make the next move"""
        return X_PLAYER if self.x_moves == self.o_moves else O_PLAYER

    @property
    def finished(self) -> bool:
        """Returns True if the game is finished"""
        return self.status != "Unfinished"

    @property
    def status(self) -> Player | Literal["Draw", "Unfinished"]:
        """Returns the winner of the game, None if the game is not yet finished"""
        for line in Move.col_lines() + Move.row_lines() + Move.diag_lines():
            cells: list[Player | None] = [self.get(move) for move in line]
            if (
                all(cells)
                and len(set(cells)) == 1
                and (winner := cells[0]) is not None
            ):
                return winner

        if self.x_moves + self.o_moves == 9:
            return "Draw"

        return "Unfinished"

    @property
    def possible_moves(self) -> list[Move]:
        """Returns the list of possible moves"""
        ret: list[Move] = []
        for row_idx, row in enumerate(self.cells):
            for col_idx, cell in enumerate(row):
                if cell is None:
                    ret.append(Move(row=row_idx, col=col_idx))
        return ret

    def get(self, move: Move) -> Player | None:
        """Returns the player who made the move"""
        return self.cells[move.row][move.col]

    def make_move(self, move: Move) -> "Board":
        """Returns a new board after making the move"""
        assert self.get(move) is None
        cells = [row.copy() for row in self.cells]
        cells[move.row][move.col] = self.player
        return Board(cells=cells)

    def to_markdown(self) -> str:
        """Prints the game board as a Markdown table"""
        ret = ""
        ret += "||A|B|C|\n"
        ret += "|---|---|---|---|\n"
        for i, row in reversed(list(enumerate(self.cells))):
            ret += f"|{i + 1}|"
            for cell in row:
                ret += f"{' ' if cell is None else _print_player(cell)}|"
            ret += "\n"
        return ret
