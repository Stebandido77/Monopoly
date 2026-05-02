"""Markov-chain approximations for Monopoly board traffic.

The chain is intentionally compact: one state per board position (40 in the
standard board). That means jail's internal three-turn substate is collapsed;
players sent to jail land on square 10 and subsequent turns treat that square
as ordinary transit. This is the "simple acceptable" model requested for the
current phase and is sufficient to recover the classic orange / jail traffic
effects once Chance / Community Chest movement cards are included.
"""

from __future__ import annotations

from collections import Counter

import numpy as np

from monopoly.board import Board

DICE_SUM_COUNTS: dict[int, int] = {
    2: 1,
    3: 2,
    4: 3,
    5: 4,
    6: 5,
    7: 6,
    8: 5,
    9: 4,
    10: 3,
    11: 2,
    12: 1,
}
DICE_SUM_PROBABILITIES: dict[int, float] = {
    total: count / 36.0 for total, count in DICE_SUM_COUNTS.items()
}
CHANCE_CARD_COUNT = 16
COMMUNITY_CHEST_CARD_COUNT = 16


def build_transition_matrix(
    board: Board,
    include_chance_effects: bool = True,
    include_jail_logic: bool = True,
) -> np.ndarray:
    """Construct the row-stochastic one-step board transition matrix.

    Parameters
    ----------
    board : Board
        Static board definition.
    include_chance_effects : bool, default=True
        Whether to fold card-driven movement from Chance / Community Chest
        into the transition probabilities.
    include_jail_logic : bool, default=True
        Reserved for future higher-fidelity jail substates. The current 40-state
        approximation collapses jail into position 10 regardless of this flag.

    Returns
    -------
    np.ndarray
        A ``(40, 40)`` matrix ``P`` where ``P[i, j]`` is the probability of
        ending a turn on square ``j`` after starting it on square ``i``.
    """

    del include_jail_logic  # 40-state model: jail is collapsed into square 10.

    n_tiles = len(board)
    matrix = np.zeros((n_tiles, n_tiles), dtype=float)

    for start in range(n_tiles):
        for dice_total, dice_prob in DICE_SUM_PROBABILITIES.items():
            landing = (start + dice_total) % n_tiles
            for destination, extra_prob in _resolve_square(
                board,
                landing,
                include_card_effects=include_chance_effects,
            ).items():
                matrix[start, destination] += dice_prob * extra_prob

    row_sums = matrix.sum(axis=1, keepdims=True)
    matrix = np.divide(matrix, row_sums, out=np.zeros_like(matrix), where=row_sums > 0)
    return matrix


def stationary_distribution(matrix: np.ndarray, tol: float = 1e-10) -> np.ndarray:
    """Compute a stationary distribution ``pi`` such that ``pi @ P = pi``.

    The primary method follows the phase spec: take the left eigenvector
    associated with eigenvalue 1. A Cesaro-averaged power iteration is used as
    a numerical fallback if the raw eigenvector is too noisy to validate.
    """

    matrix = np.asarray(matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("P must be a square matrix.")
    if np.any(matrix < -tol):
        raise ValueError("P must be non-negative.")
    if not np.allclose(matrix.sum(axis=1), 1.0, atol=tol):
        raise ValueError("P must be row-stochastic.")

    eigenvalues, eigenvectors = np.linalg.eig(matrix.T)
    idx = int(np.argmin(np.abs(eigenvalues - 1.0)))
    candidate = np.real_if_close(eigenvectors[:, idx], tol=1000).astype(float)
    if np.iscomplexobj(candidate):
        candidate = candidate.real
    if candidate.sum() < 0:
        candidate *= -1.0
    candidate = np.clip(candidate, 0.0, None)

    if candidate.sum() <= tol:
        candidate = _cesaro_stationary(matrix, tol)
    else:
        candidate /= candidate.sum()
        if np.max(np.abs(candidate @ matrix - candidate)) >= tol:
            candidate = _cesaro_stationary(matrix, tol)

    candidate = np.clip(candidate, 0.0, None)
    candidate /= candidate.sum()
    residual = np.max(np.abs(candidate @ matrix - candidate))
    if residual >= max(tol, 1e-8):
        raise ValueError(f"Stationary distribution did not converge: residual={residual}")
    return candidate


def _cesaro_stationary(matrix: np.ndarray, tol: float) -> np.ndarray:
    n_states = matrix.shape[0]
    dist = np.full(n_states, 1.0 / n_states, dtype=float)
    average = np.zeros(n_states, dtype=float)

    for step in range(1, 20_001):
        dist = dist @ matrix
        average += dist
        candidate = average / step
        if np.max(np.abs(candidate @ matrix - candidate)) < tol:
            return candidate / candidate.sum()

    return candidate / candidate.sum()


def _resolve_square(
    board: Board,
    position: int,
    include_card_effects: bool,
) -> dict[int, float]:
    tile = board.tiles[position]
    if tile.type == "go_to_jail":
        return {_jail_position(board): 1.0}
    if not include_card_effects:
        return {position: 1.0}
    if tile.type == "chance":
        return _chance_distribution(board, position)
    if tile.type == "community_chest":
        return _community_chest_distribution(board, position)
    return {position: 1.0}


def _chance_distribution(board: Board, position: int) -> dict[int, float]:
    counts: Counter[int] = Counter()

    def add(destinations: dict[int, float]) -> None:
        for destination, prob in destinations.items():
            counts[destination] += prob / CHANCE_CARD_COUNT

    add({0: 1.0})  # Advance to Go
    add({24: 1.0})  # Illinois Avenue
    add({11: 1.0})  # St. Charles Place
    add({_nearest_of_type(board, position, "utility"): 1.0})
    add({_nearest_of_type(board, position, "railroad"): 1.0})
    add({_nearest_of_type(board, position, "railroad"): 1.0})
    add({position: 1.0})  # Bank pays dividend
    add({position: 1.0})  # Get out of jail free
    add(_resolve_square(board, (position - 3) % len(board), include_card_effects=True))
    add({_jail_position(board): 1.0})  # Go to Jail
    add({position: 1.0})  # General repairs
    add({position: 1.0})  # Speeding fine
    add({5: 1.0})  # Reading Railroad
    add({39: 1.0})  # Boardwalk
    add({position: 1.0})  # Chairman of the Board
    add({position: 1.0})  # Building loan matures

    return dict(counts)


def _community_chest_distribution(board: Board, position: int) -> dict[int, float]:
    counts: Counter[int] = Counter()
    move_cards = (
        _resolve_square(board, 0, include_card_effects=True),
        {_jail_position(board): 1.0},
    )
    for destinations in move_cards:
        for destination, prob in destinations.items():
            counts[destination] += prob / COMMUNITY_CHEST_CARD_COUNT

    stationary_cards = COMMUNITY_CHEST_CARD_COUNT - len(move_cards)
    counts[position] += stationary_cards / COMMUNITY_CHEST_CARD_COUNT
    return dict(counts)


def _nearest_of_type(board: Board, position: int, tile_type: str) -> int:
    candidates = sorted(tile.position for tile in board.tiles_by_type[tile_type])
    for candidate in candidates:
        if candidate > position:
            return candidate
    return candidates[0]


def _jail_position(board: Board) -> int:
    return next(tile.position for tile in board.tiles if tile.type == "jail")
