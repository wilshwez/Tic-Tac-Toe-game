"""Pure game rules for Tic-Tac-Toe (no GUI, no I/O).

The board is a list of 9 strings: "X", "O" or "" (empty), indexed 0-8
left-to-right, top-to-bottom.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

# Same winning combinations as the original project.
WIN_LINES: Tuple[Tuple[int, int, int], ...] = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # columns
    (0, 4, 8), (2, 4, 6),             # diagonals
)


def other(symbol: str) -> str:
    """Return the opposing symbol."""
    return "O" if symbol == "X" else "X"


def winning_line(board: Sequence[str]) -> Optional[Tuple[int, int, int]]:
    """Return the winning (a, b, c) cell triple, or None."""
    for a, b, c in WIN_LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return (a, b, c)
    return None


def winner_of(board: Sequence[str]) -> Optional[str]:
    """Return "X" / "O" if someone has won, else None."""
    line = winning_line(board)
    return board[line[0]] if line else None


def empty_cells(board: Sequence[str]) -> List[int]:
    return [i for i, cell in enumerate(board) if cell == ""]


def is_full(board: Sequence[str]) -> bool:
    return "" not in board
