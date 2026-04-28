"""Smoke and invariant tests for end-to-end gameplay.

The smoke test exercises the full engine for 200 outer rounds with two
RandomStrategy players and asserts no exception is raised, plus that the
final state is exactly reproducible from the seed. The invariant test uses
hypothesis to fuzz seeds and payment counts: in any run that involves
rent transfers between players (with no bank-touching events), the sum of
player cash must be conserved.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from monopoly.board import Board
from monopoly.game import Game
from monopoly.player import Player
from monopoly.strategies import RandomStrategy


def _run_smoke(seed: int = 42, max_outer_turns: int = 200) -> tuple[Player, Player]:
    """Play up to ``max_outer_turns`` rounds with two RandomStrategy players."""
    board = Board.default()
    p1 = Player("P1")
    p2 = Player("P2")
    strategies = {"P1": RandomStrategy(), "P2": RandomStrategy()}
    game = Game([p1, p2], board, strategies=strategies, seed=seed)
    for _ in range(max_outer_turns):
        survivors = [p for p in game.players if p.cash >= 0]
        if len(survivors) <= 1:
            break
        for player in game.players:
            if player.cash < 0:
                continue
            game.play_turn(player)
    return p1, p2


def test_smoke_two_players_random_strategy_no_exceptions():
    """200 rounds with two RandomStrategy players must not raise."""
    p1, p2 = _run_smoke(seed=42, max_outer_turns=200)
    assert isinstance(p1.cash, int)
    assert isinstance(p2.cash, int)


def test_smoke_seed_42_is_reproducible():
    """Same seed -> identical final state on every replay."""
    a1, b1 = _run_smoke(seed=42)
    a2, b2 = _run_smoke(seed=42)
    state1 = (a1.cash, a1.position, b1.cash, b1.position)
    state2 = (a2.cash, a2.position, b2.cash, b2.position)
    assert state1 == state2
    assert {t.position for t in a1.properties} == {t.position for t in a2.properties}
    assert {t.position for t in b1.properties} == {t.position for t in b2.properties}


def test_smoke_different_seeds_diverge():
    """Sanity: different seeds usually produce different outcomes.

    A weak diverge check (state inequality) is sufficient — its purpose is
    to catch the case where seed plumbing is broken and the RNG is not
    actually consumed.
    """
    a1, b1 = _run_smoke(seed=42)
    a2, b2 = _run_smoke(seed=7)
    state1 = (a1.cash, a1.position, b1.cash, b1.position)
    state2 = (a2.cash, a2.position, b2.cash, b2.position)
    assert state1 != state2


def _run_5_turns(seed: int, verbose: bool) -> None:
    """Helper for verbose-mode tests: run 5 outer rounds with two players."""
    board = Board.default()
    p1 = Player("P1")
    p2 = Player("P2")
    strategies = {"P1": RandomStrategy(), "P2": RandomStrategy()}
    game = Game(
        [p1, p2], board, strategies=strategies, seed=seed, verbose=verbose
    )
    for _ in range(5):
        for player in game.players:
            if player.cash < 0:
                continue
            game.play_turn(player)


def test_verbose_false_prints_nothing(capsys):
    """With verbose=False (default), play_turn must produce no stdout."""
    _run_5_turns(seed=42, verbose=False)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_verbose_true_prints_at_least_one_line_in_5_turns(capsys):
    """With verbose=True, at least one event line is emitted within 5 rounds."""
    _run_5_turns(seed=42, verbose=True)
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) >= 1


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    seed=st.integers(min_value=0, max_value=10_000),
    n_payments=st.integers(min_value=0, max_value=100),
    dice_roll=st.integers(min_value=2, max_value=12),
)
def test_rent_only_runs_conserve_total_player_cash(
    seed: int, n_payments: int, dice_roll: int
):
    """Property: no bank traffic -> total player cash is invariant.

    Per CLAUDE.md, the engine must conserve money in scenarios that
    involve only inter-player transfers. We isolate rent by skipping
    movement and calling pay_rent directly between two players for an
    arbitrary number of payments and dice rolls.
    """
    board = Board.default()
    p1 = Player("P1", cash=10_000)
    p2 = Player("P2", cash=10_000)
    game = Game([p1, p2], board, seed=seed)
    # P1 owns all four railroads and one utility; P2 will pay rent.
    for r in board.tiles_by_type["railroad"]:
        p1.properties.append(r)
        game.owners[r.position] = p1
    util = board.tiles_by_type["utility"][0]
    p1.properties.append(util)
    game.owners[util.position] = p1

    targets = list(p1.properties)
    total_before = p1.cash + p2.cash
    for _ in range(n_payments):
        idx = int(game.rng.integers(0, len(targets)))
        game.pay_rent(p2, targets[idx], dice_roll)
    assert p1.cash + p2.cash == total_before
