from typing import List, Literal, Optional, Union

from aidial_sdk.pydantic_v1 import BaseModel

Player = Literal["X", "O"]


class Move(BaseModel):
    row: int
    col: int

    @classmethod
    def parse(cls, move: str) -> "Move":
        row_str = move[1]
        assert row_str in ["1", "2", "3"]
        row = int(row_str) - 1

        col_str = move[0]
        assert col_str in ["A", "B", "C"]
        col = {"A": 0, "B": 1, "C": 2}[col_str]

        return Move(row=row, col=col)

    def print(self) -> str:
        col = {0: "A", 1: "B", 2: "C"}[self.col]
        row = self.row + 1
        return f"{col}{row}"

    @staticmethod
    def col_lines() -> List[List["Move"]]:
        return [
            [Move(row=row, col=col) for row in range(3)] for col in range(3)
        ]

    @staticmethod
    def row_lines() -> List[List["Move"]]:
        return [
            [Move(row=row, col=col) for col in range(3)] for row in range(3)
        ]

    @staticmethod
    def diag_lines() -> List[List["Move"]]:
        return [
            [Move(row=i, col=i) for i in range(3)],
            [Move(row=i, col=2 - i) for i in range(3)],
        ]


class GameState(BaseModel):
    cells: List[List[Optional[Player]]] = [[None] * 3] * 3
    """Current state of the game board"""

    @property
    def x_moves(self) -> int:
        return sum(row.count("X") for row in self.cells)

    @property
    def o_moves(self) -> int:
        return sum(row.count("O") for row in self.cells)

    @property
    def player(self) -> Player:
        """Returns the player who should make the next move"""
        return "O" if self.x_moves == self.o_moves else "X"

    @property
    def finished(self) -> bool:
        """Returns True if the game is finished"""
        return self.status != "Unfinished"

    @property
    def status(self) -> Union[Player, Literal["Draw", "Unfinished"]]:
        """Returns the winner of the game, None if the game is not yet finished"""
        for line in Move.col_lines() + Move.row_lines() + Move.diag_lines():
            cells: List[Optional[Player]] = [self.get(move) for move in line]
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
    def possible_moves(self) -> List[Move]:
        """Returns the list of possible moves"""
        ret: List[Move] = []
        for row_idx, row in enumerate(self.cells):
            for col_idx, cell in enumerate(row):
                if cell is None:
                    ret.append(Move(row=row_idx, col=col_idx))
        return ret

    def get(self, move: Move) -> Optional[Player]:
        """Returns the player who made the move"""
        return self.cells[move.row][move.col]

    def make_move(self, move: Move) -> "GameState":
        """Returns a new game state after making the move"""
        assert self.get(move) is None
        cells = [row.copy() for row in self.cells]
        cells[move.row][move.col] = self.player
        return GameState(cells=cells)

    def print_board(self) -> str:
        """Prints the game board as a Markdown table"""
        ret = ""
        ret += "||A|B|C|\n"
        ret += "|---|---|---|---|\n"
        for i, row in reversed(list(enumerate(self.cells))):
            ret += f"|{i + 1}|"
            for cell in row:
                ret += f"{' ' if cell is None else cell}|"
            ret += "\n"
        return ret
