"""Tests for movement, the GO salary, doubles, and jail mechanics.

Each test asserts a Hasbro rule directly. Dice are forced via
monkey-patching ``game.roll_dice`` so that we exercise the policy logic
without relying on the RNG.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from monopoly.board import Board
from monopoly.game import Game
from monopoly.player import Player


@pytest.fixture
def setup() -> tuple[Game, Player, Player, Board]:
    board = Board.default()
    p1 = Player("P1")
    p2 = Player("P2")
    game = Game([p1, p2], board, seed=0)
    return game, p1, p2, board


def _force_rolls(game: Game, rolls: list[tuple[int, int]]) -> Iterator[tuple[int, int]]:
    """Patch ``game.roll_dice`` to return a fixed sequence of dice rolls."""
    seq = iter(rolls)
    game.roll_dice = lambda: next(seq)  # type: ignore[method-assign]
    return seq


def test_move_within_board_pays_no_salary(setup):
    game, p, _, _ = setup
    p.position = 5
    p.cash = 1500
    game.move_player(p, 3)
    assert p.position == 8
    assert p.cash == 1500


def test_passing_go_pays_200(setup):
    """Per Hasbro rules: $200 is paid for passing GO."""
    game, p, _, _ = setup
    p.position = 38
    p.cash = 100
    game.move_player(p, 5)  # 38 + 5 = 43 -> wraps to 3
    assert p.position == 3
    assert p.cash == 300


def test_landing_exactly_on_go_pays_200(setup):
    """Per Hasbro rules: $200 is paid for landing on GO too, not only passing."""
    game, p, _, _ = setup
    p.position = 35
    p.cash = 100
    game.move_player(p, 5)  # exactly to position 0
    assert p.position == 0
    assert p.cash == 300


def test_three_consecutive_doubles_send_to_jail(setup):
    """Per Hasbro rules: three doubles in a row in the same turn -> jail."""
    game, p, _, _ = setup
    _force_rolls(game, [(2, 2), (3, 3), (4, 4)])
    game.play_turn(p)
    assert p.in_jail is True
    assert p.position == game._jail_position
    assert p.doubles_streak == 0


def test_two_doubles_then_normal_does_not_jail(setup):
    game, p, _, _ = setup
    p.position = 0
    _force_rolls(game, [(2, 2), (3, 3), (1, 4)])
    game.play_turn(p)
    assert p.in_jail is False
    # Moved 4 + 6 + 5 = 15 tiles total within the same turn.
    assert p.position == 15


def test_doubles_grant_an_extra_roll(setup):
    """Rolling doubles lets the player roll again in the same turn."""
    game, p, _, _ = setup
    p.position = 0
    _force_rolls(game, [(2, 2), (1, 3)])
    game.play_turn(p)
    # 4 (from doubles) + 4 (from non-doubles) = 8
    assert p.position == 8


def test_landing_on_go_to_jail_tile_sends_to_jail(setup):
    game, p, _, _ = setup
    p.position = 27
    p.cash = 1500
    _force_rolls(game, [(1, 2)])  # 27 + 3 = 30 (Go to Jail)
    game.play_turn(p)
    assert p.in_jail is True
    assert p.position == game._jail_position
    assert p.doubles_streak == 0


def test_play_turn_skips_already_bankrupt_player(setup):
    """A player with cash < 0 is out and does not roll."""
    game, p, _, _ = setup
    p.cash = -1
    p.position = 5
    _force_rolls(game, [(3, 3)])
    game.play_turn(p)
    assert p.position == 5  # unchanged


def test_handle_jail_doubles_exit_resets_streak(setup):
    """Per Hasbro rules: doubles to escape jail end the turn — no bonus roll.

    The doubles_streak counter must therefore be reset so the post-jail
    move does not loop back into the bonus-roll path.
    """
    game, p, _, _ = setup
    p.in_jail = True
    p.jail_turns = 1
    p.doubles_streak = 5  # arbitrary stale value
    _force_rolls(game, [(3, 3)])
    result = game.handle_jail(p)
    assert result == (3, 3)
    assert p.in_jail is False
    assert p.jail_turns == 0
    assert p.doubles_streak == 0


def test_handle_jail_failed_first_attempt_stays_in_jail(setup):
    game, p, _, _ = setup
    p.in_jail = True
    p.jail_turns = 0
    _force_rolls(game, [(2, 5)])  # not doubles
    result = game.handle_jail(p)
    assert result is None
    assert p.in_jail is True
    assert p.jail_turns == 1


def test_handle_jail_third_failed_attempt_forces_fine(setup):
    """Per Hasbro rules: after 3 failed attempts the player must pay $50 and move."""
    game, p, _, _ = setup
    p.in_jail = True
    p.jail_turns = 2
    p.cash = 100
    _force_rolls(game, [(1, 4)])  # not doubles
    result = game.handle_jail(p)
    assert result == (1, 4)
    assert p.in_jail is False
    assert p.jail_turns == 0
    assert p.cash == 50  # 100 - 50 fine


def test_post_jail_doubles_exit_does_not_grant_bonus_turn(setup):
    """A doubles roll out of jail moves once and then the turn ends."""
    game, p, _, _ = setup
    p.in_jail = True
    p.position = 10  # Just Visiting / Jail
    # First call (inside handle_jail) returns doubles (escape). play_turn
    # must NOT call roll_dice a second time.
    rolls = [(3, 3)]
    seq = iter(rolls)

    def roll() -> tuple[int, int]:
        return next(seq)

    game.roll_dice = roll  # type: ignore[method-assign]
    game.play_turn(p)
    assert p.in_jail is False
    assert p.position == 16  # 10 + 6
    assert p.doubles_streak == 0


def test_seed_makes_dice_deterministic():
    """Same seed -> same dice sequence, regardless of player state."""
    board = Board.default()
    g1 = Game([Player("A"), Player("B")], board, seed=42)
    g2 = Game([Player("A"), Player("B")], board, seed=42)
    rolls_1 = [g1.roll_dice() for _ in range(20)]
    rolls_2 = [g2.roll_dice() for _ in range(20)]
    assert rolls_1 == rolls_2
