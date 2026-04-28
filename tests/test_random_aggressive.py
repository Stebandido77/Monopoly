"""Tests for :class:`monopoly.strategies.RandomAggressiveStrategy`."""

from __future__ import annotations

import pytest

from monopoly.board import Board, Tile
from monopoly.game import Game
from monopoly.player import Player
from monopoly.strategies.random_aggressive import (
    BUILD_PROBABILITY,
    RandomAggressiveStrategy,
)


@pytest.fixture
def setup() -> tuple[Game, Player, Board]:
    board = Board.default()
    p = Player("P", cash=10_000)
    game = Game([p], board, seed=42)
    return game, p, board


def assign_group(game: Game, player: Player, color: str) -> list[Tile]:
    tiles = list(game.board.color_groups[color])
    for t in tiles:
        player.properties.append(t)
        game.owners[t.position] = player
    return tiles


def test_purchase_always_true(setup):
    game, p, board = setup
    assert RandomAggressiveStrategy().decide_purchase(p, board.tiles[1], game) is True


def test_jail_action_always_roll(setup):
    game, p, _ = setup
    assert RandomAggressiveStrategy().decide_jail_action(p, game) == "roll"


def test_build_probability_is_higher_than_random_strategy(setup):
    """Empirically: with seed=42 and an orange monopoly, p=0.5 builds more
    tiles on average than p=0.3 over many trials."""
    from monopoly.strategies.random_strategy import RandomStrategy

    board = Board.default()
    aggressive_count = 0
    random_count = 0
    n_trials = 100
    for trial in range(n_trials):
        for label, strategy in [
            ("aggr", RandomAggressiveStrategy()),
            ("rand", RandomStrategy()),
        ]:
            p = Player("P", cash=10_000)
            game = Game([p], board, seed=trial)
            assign_group(game, p, "orange")
            built = strategy.decide_build(p, game)
            if label == "aggr":
                aggressive_count += len(built)
            else:
                random_count += len(built)
    # Over 100 seeds, p=0.5 should produce strictly more builds than p=0.3.
    assert aggressive_count > random_count


def test_build_returns_empty_without_monopoly(setup):
    game, p, _ = setup
    p.properties.append(game.board.tiles[1])
    game.owners[1] = p
    assert RandomAggressiveStrategy().decide_build(p, game) == []


def test_build_skips_when_cash_too_low(setup):
    """Spec gates by cash > house_cost * 2."""
    game, p, _ = setup
    assign_group(game, p, "brown")  # house_cost 50 → threshold 100
    p.cash = 100  # exactly the threshold (strict <=)
    assert RandomAggressiveStrategy().decide_build(p, game) == []


def test_build_uses_game_rng_for_determinism(setup):
    """Same seed → same build decision."""
    board = Board.default()
    results = []
    for _ in range(2):
        p = Player("P", cash=10_000)
        game = Game([p], board, seed=42)
        assign_group(game, p, "orange")
        results.append([t.position for t in RandomAggressiveStrategy().decide_build(p, game)])
    assert results[0] == results[1]


def test_build_probability_constant():
    assert BUILD_PROBABILITY == 0.5
