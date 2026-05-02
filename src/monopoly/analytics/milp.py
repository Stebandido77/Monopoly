"""MILP-based initial portfolio optimization for Monopoly streets."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pulp

from monopoly.board import Board, Tile


@dataclass(frozen=True)
class MILPSolution:
    """Solved purchase / development plan for a single player."""

    purchase: dict[int, bool]
    houses: dict[int, int]
    hotel: dict[int, bool]
    expected_rent_per_turn: float
    total_cost: int
    solver_status: str


def optimize_initial_purchase(
    board: Board,
    budget: int,
    stationary_dist: np.ndarray,
    available_tiles: list[int] | None = None,
    time_limit_seconds: int = 30,
) -> MILPSolution:
    """Solve the optimal street-purchase / development mix under a budget.

    Notes
    -----
    The plan uses a one-hot development level per street:

    * ``0``: bought, undeveloped
    * ``1..4``: number of houses
    * ``5``: hotel

    In the returned solution, ``houses[pos] == 4`` together with
    ``hotel[pos] is True`` means "build through the full ladder to a hotel".
    This matches the game engine's need to construct the four houses before the
    hotel even though the *final* on-board house count becomes zero.
    """

    stationary = np.asarray(stationary_dist, dtype=float)
    if stationary.shape != (len(board),):
        raise ValueError("stationary_dist must have one probability per board tile.")
    if budget < 0:
        raise ValueError("budget must be non-negative.")

    candidate_tiles = _candidate_streets(board, available_tiles)
    if not candidate_tiles:
        return MILPSolution(
            purchase={},
            houses={},
            hotel={},
            expected_rent_per_turn=0.0,
            total_cost=0,
            solver_status="Optimal",
        )

    model = pulp.LpProblem("MonopolyInitialPurchase", pulp.LpMaximize)
    levels = range(6)
    candidate_positions = {tile.position for tile in candidate_tiles}

    buy = {
        tile.position: pulp.LpVariable(f"buy_{tile.position}", cat="Binary")
        for tile in candidate_tiles
    }
    level = {
        (tile.position, k): pulp.LpVariable(f"level_{tile.position}_{k}", cat="Binary")
        for tile in candidate_tiles
        for k in levels
    }
    undeveloped_monopoly = {
        tile.position: pulp.LpVariable(f"bonus_{tile.position}", cat="Binary")
        for tile in candidate_tiles
    }
    monopoly = {
        color: pulp.LpVariable(f"monopoly_{color}", cat="Binary")
        for color in board.color_groups
    }

    for tile in candidate_tiles:
        pos = tile.position
        model += pulp.lpSum(level[pos, k] for k in levels) == buy[pos]

    objective_terms: list[pulp.LpAffineExpression] = []
    total_cost_terms: list[pulp.LpAffineExpression] = []

    for tile in candidate_tiles:
        assert tile.rent is not None
        assert tile.color_group is not None
        pos = tile.position
        base_rent = tile.rent[0]
        build_cost = tile.house_cost or 0
        total_cost_terms.append(tile.price * buy[pos])
        total_cost_terms.extend(
            build_cost * k * level[pos, k] for k in range(1, 5)
        )
        total_cost_terms.append(build_cost * 5 * level[pos, 5])

        objective_terms.append(stationary[pos] * base_rent * level[pos, 0])
        objective_terms.extend(
            stationary[pos] * tile.rent[k] * level[pos, k] for k in range(1, 6)
        )
        objective_terms.append(
            stationary[pos] * base_rent * undeveloped_monopoly[pos]
        )

        color = tile.color_group
        developed = pulp.lpSum(level[pos, k] for k in range(1, 6))
        model += developed <= monopoly[color]
        model += undeveloped_monopoly[pos] <= level[pos, 0]
        model += undeveloped_monopoly[pos] <= monopoly[color]
        model += undeveloped_monopoly[pos] >= level[pos, 0] + monopoly[color] - 1

    model += pulp.lpSum(total_cost_terms) <= budget
    model += (
        pulp.lpSum(
            k * level[tile.position, k]
            for tile in candidate_tiles
            for k in range(1, 5)
        )
        <= board.bank.total_houses
    )
    model += (
        pulp.lpSum(level[tile.position, 5] for tile in candidate_tiles)
        <= board.bank.total_hotels
    )

    for color, group_tiles in board.color_groups.items():
        group_positions = [tile.position for tile in group_tiles]
        if not set(group_positions).issubset(candidate_positions):
            model += monopoly[color] == 0
        else:
            model += monopoly[color] >= pulp.lpSum(buy[pos] for pos in group_positions) - (
                len(group_positions) - 1
            )
            for pos in group_positions:
                model += monopoly[color] <= buy[pos]

            for idx, left_pos in enumerate(group_positions):
                left_level = pulp.lpSum(k * level[left_pos, k] for k in levels)
                for right_pos in group_positions[idx + 1 :]:
                    right_level = pulp.lpSum(k * level[right_pos, k] for k in levels)
                    model += left_level - right_level <= 1
                    model += right_level - left_level <= 1

    model += pulp.lpSum(objective_terms)

    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit_seconds)
    model.solve(solver)
    solver_status = pulp.LpStatus[model.status]

    purchase: dict[int, bool] = {}
    houses: dict[int, int] = {}
    hotel: dict[int, bool] = {}
    total_cost = 0

    for tile in candidate_tiles:
        pos = tile.position
        purchase[pos] = _binary_value(buy[pos])
        selected_level = 0
        for k in levels:
            if _binary_value(level[pos, k]):
                selected_level = k
                break

        hotel[pos] = selected_level == 5
        houses[pos] = 4 if selected_level == 5 else selected_level
        if purchase[pos]:
            total_cost += tile.price or 0
            total_cost += (tile.house_cost or 0) * houses[pos]
            if hotel[pos]:
                total_cost += tile.house_cost or 0

    objective_value = float(pulp.value(model.objective) or 0.0)
    return MILPSolution(
        purchase=purchase,
        houses=houses,
        hotel=hotel,
        expected_rent_per_turn=objective_value,
        total_cost=total_cost,
        solver_status=solver_status,
    )


def _candidate_streets(board: Board, available_tiles: list[int] | None) -> list[Tile]:
    streets = [tile for tile in board.tiles if tile.type == "street"]
    if available_tiles is None:
        return streets

    allowed = set(available_tiles)
    return [tile for tile in streets if tile.position in allowed]


def _binary_value(variable: pulp.LpVariable) -> bool:
    value = pulp.value(variable)
    return bool(value is not None and value >= 0.5)
