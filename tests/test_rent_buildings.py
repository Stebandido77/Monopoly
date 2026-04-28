"""Tests for rent calculation with houses and hotels (Phase 2, Part B).

Each test reads the rent schedule directly from ``data/board.yaml`` via the
loaded :class:`Tile` and asserts that the engine's rent matches the
corresponding entry. The monopoly-doubling rule is preserved only for the
unbuilt-monopoly case (per Hasbro rules: "the rent doubles if you own all
the lots of any color group, except those mortgaged"). With any building
on the tile, the printed rent[1..5] schedule applies as-is.
"""

from __future__ import annotations

import pytest

from monopoly.board import Board, Tile
from monopoly.game import Game
from monopoly.player import Player


@pytest.fixture
def setup() -> tuple[Game, Player, Player, Board]:
    board = Board.default()
    p1 = Player("P1", cash=20_000)
    p2 = Player("P2", cash=20_000)
    game = Game([p1, p2], board, seed=0)
    return game, p1, p2, board


def assign(game: Game, player: Player, tile: Tile) -> None:
    player.properties.append(tile)
    game.owners[tile.position] = player


def assign_brown(game: Game, player: Player) -> tuple[Tile, Tile]:
    med = game.board.tiles[1]
    baltic = game.board.tiles[3]
    assign(game, player, med)
    assign(game, player, baltic)
    return med, baltic


def test_one_house_uses_rent_index_one(setup):
    """Mediterranean Avenue: $10 rent with 1 house (per board.yaml)."""
    game, p1, _, _ = setup
    med, _ = assign_brown(game, p1)
    p1.build_house(med)
    assert game.calculate_rent(med, 0) == med.rent[1]
    assert med.rent[1] == 10


def test_two_houses_use_rent_index_two(setup):
    game, p1, _, _ = setup
    med, baltic = assign_brown(game, p1)
    p1.build_house(med)
    p1.build_house(baltic)
    p1.build_house(med)
    assert game.calculate_rent(med, 0) == med.rent[2]
    assert med.rent[2] == 30


def test_four_houses_use_rent_index_four(setup):
    game, p1, _, _ = setup
    med, baltic = assign_brown(game, p1)
    for _ in range(4):
        p1.build_house(med)
        p1.build_house(baltic)
    assert game.calculate_rent(med, 0) == med.rent[4]
    assert med.rent[4] == 160


def test_hotel_uses_rent_index_five(setup):
    """Per Hasbro rules: hotel rent is the last entry of the schedule."""
    game, p1, _, _ = setup
    med, baltic = assign_brown(game, p1)
    for _ in range(4):
        p1.build_house(med)
        p1.build_house(baltic)
    p1.build_hotel(med)
    assert game.calculate_rent(med, 0) == med.rent[5]
    assert med.rent[5] == 250


def test_monopoly_doubling_rule_preserved_when_unbuilt(setup):
    """An unbuilt monopoly still doubles the base rent."""
    game, p1, _, _ = setup
    med, _ = assign_brown(game, p1)
    assert game.calculate_rent(med, 0) == med.rent[0] * 2  # 4


def test_no_doubling_once_houses_are_built(setup):
    """The doubling stops once any house is on the tile (it's already in rent[1..])."""
    game, p1, _, _ = setup
    med, baltic = assign_brown(game, p1)
    p1.build_house(med)
    # rent[1] = 10, NOT 10*2.
    assert game.calculate_rent(med, 0) == med.rent[1]


def test_pay_rent_charges_full_building_amount(setup):
    """Renting a hotel'd Boardwalk costs $2000."""
    game, p1, p2, _ = setup
    bw = game.board.tiles[39]
    park = game.board.tiles[37]
    for tile in (bw, park):
        assign(game, p1, tile)
    for _ in range(4):
        p1.build_house(bw)
        p1.build_house(park)
    p1.build_hotel(bw)
    p2.cash = 5000
    cash_before = p2.cash
    rent = game.pay_rent(p2, bw, 0)
    assert rent == 2000
    assert p2.cash == cash_before - 2000
