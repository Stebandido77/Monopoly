"""Tests for mortgages and unmortgages (Phase 2, Part C).

Each test asserts a Hasbro rule directly. Mortgaged properties charge no
rent (also covered in tests/test_rent_buildings.py). Unmortgaging costs
``mortgage_value × 1.10`` rounded *up* to the nearest dollar.
"""

from __future__ import annotations

import math

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
    player.properties.append(tile)
    game.owners[tile.position] = player


# --- mortgage ---------------------------------------------------------------


def test_mortgage_pays_mortgage_value(setup):
    """Per Hasbro rules: mortgaging credits the listed mortgage value."""
    game, p1, _, board = setup
    med = board.tiles[1]  # mortgage_value = 30
    assign(game, p1, med)
    cash_before = p1.cash
    assert p1.mortgage(med) is True
    assert game.mortgaged[med.position] is True
    assert p1.cash == cash_before + 30


def test_cannot_mortgage_already_mortgaged(setup):
    game, p1, _, board = setup
    med = board.tiles[1]
    assign(game, p1, med)
    p1.mortgage(med)
    assert p1.mortgage(med) is False


def test_cannot_mortgage_property_not_owned(setup):
    game, p1, _, board = setup
    med = board.tiles[1]
    assert p1.mortgage(med) is False


def test_cannot_mortgage_with_buildings_in_group(setup):
    """Per Hasbro rules: must sell every building in the group first."""
    game, p1, _, board = setup
    # Give P1 the brown monopoly and build one house on Mediterranean.
    med = board.tiles[1]
    baltic = board.tiles[3]
    for tile in (med, baltic):
        assign(game, p1, tile)
    p1.build_house(med)
    # Cannot mortgage Baltic while Mediterranean has a house.
    assert p1.mortgage(baltic) is False
    # Sell the house, then mortgaging is allowed.
    p1.sell_house(med)
    assert p1.mortgage(baltic) is True


def test_railroad_mortgage_works_independently(setup):
    """Railroads have no buildings, so the group-rule does not apply."""
    game, p1, _, board = setup
    rr = board.tiles_by_type["railroad"][0]
    assign(game, p1, rr)
    assert p1.mortgage(rr) is True
    assert game.mortgaged[rr.position] is True


# --- unmortgage --------------------------------------------------------------


def test_unmortgage_costs_value_plus_ten_percent_rounded_up(setup):
    """Per Hasbro rules: lifting a mortgage costs ``mortgage × 1.10``.

    Rounding is up to the next dollar (so $30 → $33 cleanly, but $35 →
    $39 because $35 × 1.10 = $38.50 → $39).
    """
    game, p1, _, board = setup
    # Mediterranean: mortgage_value=30 → 30*1.10 = 33 (clean integer).
    med = board.tiles[1]
    assign(game, p1, med)
    p1.mortgage(med)
    cash_before = p1.cash
    assert p1.unmortgage(med) is True
    assert game.mortgaged[med.position] is False
    assert p1.cash == cash_before - 33

    # Use a value that requires ceiling rounding: pick a fake price 35.
    # Pennsylvania Railroad has mortgage_value=100 → 100 * 1.10 = 110 (clean).
    # Constructing a non-clean case directly with the canonical board:
    # pos 9 (Connecticut) has mortgage_value=60 → 66 (clean).
    # All current board values produce clean results. Verify ceil() logic by
    # patching one tile temporarily — done in test_unmortgage_ceiling below.


def test_unmortgage_ceiling_logic_via_math():
    """Sanity: ceil(35 * 1.10) == 39, not 38, regardless of float drift."""
    assert math.ceil(35 * 1.10) == 39
    assert math.ceil(75 * 1.10) == 83  # utility mortgage 75


def test_unmortgage_utility_uses_ceiling(setup):
    """Utility mortgage 75 → unmortgage cost is ceil(75 * 1.10) = 83."""
    game, p1, _, board = setup
    util = board.tiles[12]  # Electric Company, mortgage_value=75
    assign(game, p1, util)
    p1.mortgage(util)
    cash_before = p1.cash
    assert p1.unmortgage(util) is True
    assert p1.cash == cash_before - 83


def test_cannot_unmortgage_unmortgaged_property(setup):
    game, p1, _, board = setup
    med = board.tiles[1]
    assign(game, p1, med)
    assert p1.unmortgage(med) is False


def test_cannot_unmortgage_without_cash(setup):
    game, p1, _, board = setup
    med = board.tiles[1]
    assign(game, p1, med)
    p1.mortgage(med)
    p1.cash = 10  # need 33 to unmortgage
    assert p1.unmortgage(med) is False
    assert game.mortgaged[med.position] is True


# --- rent interaction --------------------------------------------------------


def test_mortgaged_property_charges_no_rent(setup):
    """Per Hasbro rules: a mortgaged property does not collect rent."""
    game, p1, p2, board = setup
    med = board.tiles[1]
    assign(game, p1, med)
    p1.mortgage(med)
    rent = game.pay_rent(p2, med, 0)
    assert rent == 0


def test_mortgaged_railroad_does_not_count_for_rent(setup):
    """Railroad rent counts only unmortgaged railroads of the same owner."""
    game, p1, p2, board = setup
    rrs = board.tiles_by_type["railroad"]
    for r in rrs:
        assign(game, p1, r)
    # All four owned: rent on rrs[0] is $200.
    assert game.calculate_rent(rrs[0], 0) == 200
    # Mortgage one of them: count drops to 3, rent on the unmortgaged ones is $100.
    p1.mortgage(rrs[1])
    assert game.calculate_rent(rrs[0], 0) == 100
    # Rent on the mortgaged one is $0.
    assert game.calculate_rent(rrs[1], 0) == 0
