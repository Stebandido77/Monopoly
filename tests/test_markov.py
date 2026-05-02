"""Tests for Monopoly board Markov analysis."""

from __future__ import annotations

import hypothesis.strategies as st
import numpy as np
from hypothesis import given

from monopoly.analytics.markov import build_transition_matrix, stationary_distribution
from monopoly.board import Board


def test_transition_matrix_is_row_stochastic():
    board = Board.default()
    matrix = build_transition_matrix(board)
    assert matrix.shape == (40, 40)
    assert np.all(matrix >= 0.0)
    assert np.allclose(matrix.sum(axis=1), 1.0, atol=1e-12)


def test_stationary_distribution_sums_to_one():
    board = Board.default()
    matrix = build_transition_matrix(board)
    stationary = stationary_distribution(matrix)
    assert np.isclose(stationary.sum(), 1.0)
    assert np.all(stationary >= 0.0)


def test_orange_group_above_uniform_average():
    board = Board.default()
    matrix = build_transition_matrix(board)
    stationary = stationary_distribution(matrix)
    uniform = 1.0 / len(board)
    for position in (16, 18, 19):
        assert stationary[position] > uniform


def test_jail_above_uniform_average():
    board = Board.default()
    matrix = build_transition_matrix(board)
    stationary = stationary_distribution(matrix)
    assert stationary[10] > 1.0 / len(board)


@st.composite
def stochastic_matrices(draw) -> np.ndarray:
    size = draw(st.integers(min_value=2, max_value=6))
    rows: list[list[float]] = []
    for _ in range(size):
        row = draw(
            st.lists(
                st.floats(
                    min_value=1e-6,
                    max_value=1.0,
                    allow_nan=False,
                    allow_infinity=False,
                ),
                min_size=size,
                max_size=size,
            )
        )
        rows.append(row)
    matrix = np.asarray(rows, dtype=float)
    matrix /= matrix.sum(axis=1, keepdims=True)
    return matrix


@given(stochastic_matrices())
def test_stationary_distribution_valid_for_random_stochastic_matrix(matrix: np.ndarray):
    stationary = stationary_distribution(matrix)
    assert np.all(stationary >= 0.0)
    assert np.isclose(stationary.sum(), 1.0)
    assert np.max(np.abs(stationary @ matrix - stationary)) < 1e-8
