"""Tests for the Monopoly MILP optimizer."""

from __future__ import annotations

from functools import lru_cache

from monopoly.analytics.markov import build_transition_matrix, stationary_distribution
from monopoly.analytics.milp import optimize_initial_purchase
from monopoly.board import Board


@lru_cache(maxsize=1)
def _stationary() -> tuple[Board, object]:
    board = Board.default()
    stationary = stationary_distribution(build_transition_matrix(board))
    return board, stationary


def test_budget_1500_returns_feasible_optimal_solution():
    board, stationary = _stationary()
    solution = optimize_initial_purchase(board, 1500, stationary)
    assert solution.solver_status == "Optimal"
    assert solution.total_cost <= 1500
    assert any(solution.purchase.values())


def test_no_building_without_monopoly():
    board, stationary = _stationary()
    solution = optimize_initial_purchase(board, 1500, stationary)
    for color, group in board.color_groups.items():
        purchased = [solution.purchase.get(tile.position, False) for tile in group]
        has_building = any(
            solution.houses.get(tile.position, 0) > 0 or solution.hotel.get(tile.position, False)
            for tile in group
        )
        if has_building:
            assert all(purchased), color


def test_hotel_targets_imply_four_houses_first():
    board, stationary = _stationary()
    solution = optimize_initial_purchase(board, 10_000, stationary)
    for position, has_hotel in solution.hotel.items():
        if has_hotel:
            assert solution.houses[position] == 4


def test_small_budget_buys_very_little():
    board, stationary = _stationary()
    solution = optimize_initial_purchase(board, 100, stationary)
    assert solution.total_cost <= 100
    assert sum(solution.purchase.values()) <= 1
    assert not any(solution.hotel.values())
    assert all(houses == 0 for houses in solution.houses.values())


def test_large_budget_buys_almost_everything_and_builds_aggressively():
    board, stationary = _stationary()
    solution = optimize_initial_purchase(board, 10_000, stationary)
    purchase_count = sum(solution.purchase.values())
    effective_levels = sum(
        5 if solution.hotel[position] else solution.houses[position]
        for position, purchased in solution.purchase.items()
        if purchased
    )
    assert solution.solver_status == "Optimal"
    assert purchase_count >= 10
    assert effective_levels >= 20
    assert solution.total_cost >= 9_000
