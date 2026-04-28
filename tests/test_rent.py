"""Tests for rent calculation and simple bankruptcy.

These tests target the rules engine directly: properties are placed via a
small helper that bypasses :meth:`Game.buy_property`, so ownership setup is
independent of any strategy. Each test names the Hasbro rule it asserts.
"""

from __future__ import annotations

import pytest

from monopoly.board import Board, Tile
from monopoly.game import Game
from monopoly.player import Player


@pytest.fixture
def setup() -> tuple[Game, Player, Player, Board]:
    board = Board.default()
    p1 = Player("P1", cash=2000)
    p2 = Player("P2", cash=2000)
    game = Game([p1, p2], board, seed=0)
    return game, p1, p2, board


def assign(game: Game, player: Player, tile: Tile) -> None:
    """Force-assign a tile to a player (skipping the strategy-driven buy)."""
    player.properties.append(tile)
    game.owners[tile.position] = player


# --- streets ----------------------------------------------------------------


def test_no_rent_when_tile_unowned(setup):
    game, _, _, board = setup
    assert game.calculate_rent(board.tiles[1], 0) == 0


def test_no_rent_when_landing_on_own_property(setup):
    game, p1, _, board = setup
    tile = board.tiles[1]
    assign(game, p1, tile)
    cash_before = p1.cash
    assert game.pay_rent(p1, tile, 0) == 0
    assert p1.cash == cash_before


def test_basic_street_rent_no_monopoly(setup):
    """Mediterranean Avenue: $2 base rent when the brown group is split."""
    game, p1, p2, board = setup
    med = board.tiles[1]
    assign(game, p1, med)
    rent = game.pay_rent(p2, med, 0)
    assert rent == 2
    assert p1.cash == 2002
    assert p2.cash == 1998


def test_double_rent_on_complete_color_group(setup):
    """Per Hasbro rules: rent doubles on a complete group with no buildings."""
    game, p1, p2, board = setup
    med = board.tiles[1]
    baltic = board.tiles[3]
    assign(game, p1, med)
    assign(game, p1, baltic)
    assert game.pay_rent(p2, med, 0) == 4  # 2 * 2
    assert game.calculate_rent(baltic, 0) == 8  # 4 * 2


def test_no_double_rent_when_group_split_between_players(setup):
    game, p1, p2, board = setup
    assign(game, p1, board.tiles[1])  # Mediterranean
    assign(game, p2, board.tiles[3])  # Baltic with rival
    rent = game.pay_rent(p2, board.tiles[1], 0)
    assert rent == 2  # not doubled


# --- railroads --------------------------------------------------------------


def test_railroad_rent_one_owned(setup):
    """Per Hasbro rules: $25 for one railroad."""
    game, p1, _, board = setup
    rrs = board.tiles_by_type["railroad"]
    assign(game, p1, rrs[0])
    assert game.calculate_rent(rrs[0], 0) == 25


def test_railroad_rent_two_owned(setup):
    """Per Hasbro rules: $50 each for two railroads."""
    game, p1, _, board = setup
    rrs = board.tiles_by_type["railroad"]
    assign(game, p1, rrs[0])
    assign(game, p1, rrs[1])
    assert game.calculate_rent(rrs[0], 0) == 50
    assert game.calculate_rent(rrs[1], 0) == 50


def test_railroad_rent_three_owned(setup):
    """Per Hasbro rules: $100 each for three railroads."""
    game, p1, _, board = setup
    rrs = board.tiles_by_type["railroad"]
    for r in rrs[:3]:
        assign(game, p1, r)
    assert game.calculate_rent(rrs[0], 0) == 100


def test_railroad_rent_four_owned(setup):
    """Per Hasbro rules: $200 each for all four railroads."""
    game, p1, _, board = setup
    rrs = board.tiles_by_type["railroad"]
    for r in rrs:
        assign(game, p1, r)
    assert game.calculate_rent(rrs[0], 0) == 200


# --- utilities --------------------------------------------------------------


def test_utility_rent_one_owned_is_4x_dice(setup):
    """Per Hasbro rules: 4x the dice roll when one utility is owned."""
    game, p1, _, board = setup
    util = board.tiles_by_type["utility"][0]
    assign(game, p1, util)
    assert game.calculate_rent(util, dice_roll=7) == 28
    assert game.calculate_rent(util, dice_roll=2) == 8


def test_utility_rent_both_owned_is_10x_dice(setup):
    """Per Hasbro rules: 10x the dice roll when both utilities are owned."""
    game, p1, _, board = setup
    utils = board.tiles_by_type["utility"]
    assign(game, p1, utils[0])
    assign(game, p1, utils[1])
    assert game.calculate_rent(utils[0], dice_roll=8) == 80
    assert game.calculate_rent(utils[1], dice_roll=12) == 120


# --- bankruptcy -------------------------------------------------------------


def test_bankrupt_player_returns_properties_to_the_bank(setup):
    game, p1, _, board = setup
    tile = board.tiles[1]
    assign(game, p1, tile)
    p1.cash = -10
    assert game.check_bankruptcy(p1) is True
    assert game.owners[tile.position] is None
    assert p1.properties == []


def test_player_with_zero_cash_is_not_bankrupt(setup):
    """Per Hasbro rules: a debt is settled if cash equals it; only negatives are bankruptcy."""
    game, p1, _, _ = setup
    p1.cash = 0
    assert game.check_bankruptcy(p1) is False


def test_player_with_positive_cash_is_not_bankrupt(setup):
    game, p1, _, _ = setup
    p1.cash = 1
    assert game.check_bankruptcy(p1) is False


def test_rent_can_drive_payer_into_bankruptcy(setup):
    """Per Hasbro rules: if a player cannot pay rent they go bankrupt."""
    game, p1, p2, board = setup
    rrs = board.tiles_by_type["railroad"]
    for r in rrs:
        assign(game, p1, r)  # P1 owns all four → $200 rent each
    p2.cash = 100
    paid = game.pay_rent(p2, rrs[0], 0)
    assert paid == 200
    assert p2.cash == -100
    assert game.check_bankruptcy(p2) is True
