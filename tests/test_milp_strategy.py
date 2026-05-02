"""Tests for :class:`monopoly.strategies.milp_optimal.MILPStrategy`."""

from __future__ import annotations

from monopoly.board import Board
from monopoly.game import Game
from monopoly.player import Player
from monopoly.simulation import MonteCarloRunner
from monopoly.strategies import (
    AggressiveStrategy,
    CautiousStrategy,
    MILPStrategy,
    RandomStrategy,
)


def test_plan_recommends_at_least_one_early_purchase():
    board = Board.default()
    player = Player("milp")
    game = Game([player], board, strategies={"milp": MILPStrategy()}, seed=42)
    strategy = game.strategies["milp"]

    recommendations = [
        strategy.decide_purchase(player, tile, game)
        for tile in board.tiles
        if tile.type == "street"
    ]
    assert any(recommendations)


def test_decide_purchase_matches_cached_plan():
    board = Board.default()
    player = Player("milp")
    strategy = MILPStrategy()
    game = Game([player], board, strategies={"milp": strategy}, seed=42)

    observed = {
        tile.position: strategy.decide_purchase(player, tile, game)
        for tile in board.tiles
        if tile.type == "street"
    }
    assert strategy._plan is not None
    assert observed == strategy._plan.solution.purchase


def test_game_with_milp_strategy_runs_200_turns_without_exceptions():
    board = Board.default()
    players = [
        Player("milp"),
        Player("cautious"),
        Player("aggressive"),
        Player("random"),
    ]
    strategies = {
        "milp": MILPStrategy(),
        "cautious": CautiousStrategy(),
        "aggressive": AggressiveStrategy(),
        "random": RandomStrategy(),
    }
    game = Game(players, board, strategies=strategies, seed=42)
    winner = game.play(max_turns=200)
    assert winner is None or winner in players


def test_runner_with_milp_strategy_completes_100_games_without_errors():
    runner = MonteCarloRunner(
        [
            ("milp", MILPStrategy),
            ("cautious", CautiousStrategy),
            ("aggressive", AggressiveStrategy),
            ("random", RandomStrategy),
        ],
        n_games=100,
        max_turns=200,
        seed=42,
        n_workers=1,
    )
    df = runner.run()
    assert len(df) == 100
    assert "error" not in set(df["end_reason"])
