"""Computer opponent: Easy, Medium and Hard.

* Easy   - random legal move (same as the original project).
* Medium - win if possible, otherwise block, otherwise random (same as original).
* Hard   - minimax with alpha-beta pruning. It never loses.

NOTE: the original ``minimax`` returned ``1 if is_maximizing else -1`` when it
found a winner, which is inverted (it scored the AI's own wins as -1). Here the
score is always computed from the AI's point of view, and quicker wins /
slower losses are preferred.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

from .logic import empty_cells, is_full, other, winner_of

DIFFICULTIES = ("Easy", "Medium", "Hard")

_INF = float("inf")


def easy_move(board: List[str], ai: str = "O", rng=random) -> Optional[int]:
    """Random legal move."""
    cells = empty_cells(board)
    return rng.choice(cells) if cells else None


def _winning_move_for(board: List[str], symbol: str) -> Optional[int]:
    for i in empty_cells(board):
        board[i] = symbol
        won = winner_of(board) == symbol
        board[i] = ""
        if won:
            return i
    return None


def medium_move(board: List[str], ai: str = "O", rng=random) -> Optional[int]:
    """Take a win, else block the opponent's win, else random."""
    cells = empty_cells(board)
    if not cells:
        return None
    move = _winning_move_for(board, ai)
    if move is None:
        move = _winning_move_for(board, other(ai))
    return move if move is not None else rng.choice(cells)


def minimax(board: List[str], to_move: str, ai: str, depth: int = 0,
            alpha: float = -_INF, beta: float = _INF) -> int:
    """Score `board` from the AI's perspective (higher is better for `ai`).

    `board` is mutated during the search but always restored.
    """
    won = winner_of(board)
    if won == ai:
        return 10 - depth
    if won is not None:
        return depth - 10
    if is_full(board):
        return 0

    if to_move == ai:
        best = -_INF
        for i in empty_cells(board):
            board[i] = to_move
            best = max(best, minimax(board, other(to_move), ai, depth + 1, alpha, beta))
            board[i] = ""
            alpha = max(alpha, best)
            if alpha >= beta:
                break
        return best

    best = _INF
    for i in empty_cells(board):
        board[i] = to_move
        best = min(best, minimax(board, other(to_move), ai, depth + 1, alpha, beta))
        board[i] = ""
        beta = min(beta, best)
        if alpha >= beta:
            break
    return best


def hard_move(board: List[str], ai: str = "O", rng=random) -> Optional[int]:
    """Perfect play. Ties between equally good moves are broken randomly."""
    cells = empty_cells(board)
    if not cells:
        return None
    if len(cells) == 9:
        # Every opening is a draw against perfect play; corners/centre give
        # a human opponent the most chances to go wrong.
        return rng.choice([0, 2, 4, 6, 8])

    scores: Dict[int, int] = {}
    for i in cells:
        board[i] = ai
        # Full window per root move => each score is exact, so ties are real.
        scores[i] = minimax(board, other(ai), ai, depth=1)
        board[i] = ""
    best = max(scores.values())
    return rng.choice([i for i, s in scores.items() if s == best])


_STRATEGIES = {"Easy": easy_move, "Medium": medium_move, "Hard": hard_move}


def choose_move(board: List[str], ai: str, difficulty: str, rng=random) -> Optional[int]:
    """Pick a cell index for `ai` at the given difficulty (None if board full)."""
    try:
        strategy = _STRATEGIES[difficulty]
    except KeyError:
        raise ValueError(f"Unknown difficulty: {difficulty!r}") from None
    return strategy(list(board), ai, rng)
