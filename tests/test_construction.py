"""Tests for house and hotel construction (Phase 2, Part A).

Each test names the Hasbro rule it asserts. Property-based invariants for
bank inventory and uniformity live alongside the unit tests at the bottom
of the file.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from monopoly.board import Board, Tile
from monopoly.game import Game
from monopoly.player import Player


@pytest.fixture
def setup() -> tuple[Game, Player, Player, Board]:
    board = Board.default()
    p1 = Player("P1", cash=10_000)
    p2 = Player("P2", cash=10_000)
    game = Game([p1, p2], board, seed=0)
    return game, p1, p2, board


def assign_group(game: Game, player: Player, color: str) -> list[Tile]:
    """Force-assign every tile of ``color`` to ``player`` and return them."""
    tiles = list(game.board.color_groups[color])
    for tile in tiles:
        player.properties.append(tile)
        game.owners[tile.position] = player
    return tiles


# --- monopoly requirement ----------------------------------------------------


def test_cannot_build_without_monopoly(setup):
    """Per Hasbro rules: building requires owning the full color group."""
    game, p1, _, _ = setup
    med = game.board.tiles[1]  # brown — Mediterranean only, not Baltic
    p1.properties.append(med)
    game.owners[med.position] = p1
    assert p1.build_house(med) is False
    assert game.houses[med.position] == 0
    assert game.available_houses == 32  # untouched


def test_build_house_succeeds_on_complete_monopoly(setup):
    """Owner with full brown group can build, paying $50 per house."""
    game, p1, _, _ = setup
    med, baltic = assign_group(game, p1, "brown")
    cash_before = p1.cash
    assert p1.build_house(med) is True
    assert game.houses[med.position] == 1
    assert p1.cash == cash_before - med.house_cost
    assert game.available_houses == 31


# --- uniformity --------------------------------------------------------------


def test_uniform_building_blocks_skipping(setup):
    """Per Hasbro rules: max(houses) - min(houses) <= 1 within a group."""
    game, p1, _, _ = setup
    med, baltic = assign_group(game, p1, "brown")
    assert p1.build_house(med) is True  # (1, 0)
    # Building a second house on Mediterranean would jump to (2, 0): blocked.
    assert p1.build_house(med) is False
    # Build on Baltic to reach (1, 1).
    assert p1.build_house(baltic) is True
    # Now Mediterranean can go to 2 (state (2, 1)).
    assert p1.build_house(med) is True
    assert game.houses[med.position] == 2
    assert game.houses[baltic.position] == 1


def test_uniform_selling_blocks_unbalanced_sales(setup):
    """Selling cannot create a >1 imbalance either."""
    game, p1, _, _ = setup
    med, baltic = assign_group(game, p1, "brown")
    p1.build_house(med)
    p1.build_house(baltic)
    p1.build_house(med)  # state (2, 1)
    # Selling Baltic's house drops to (2, 0): blocked.
    assert p1.sell_house(baltic) is False
    # Selling Mediterranean's house drops to (1, 1): allowed.
    assert p1.sell_house(med) is True
    assert game.houses[med.position] == 1
    assert game.houses[baltic.position] == 1


# --- hotel mechanics ---------------------------------------------------------


def test_hotel_requires_four_houses(setup):
    """Per Hasbro rules: a hotel is the fifth construction (after 4 houses)."""
    game, p1, _, _ = setup
    med, baltic = assign_group(game, p1, "brown")
    # Build 4 houses on each (cost is 8 * 50 = 400).
    for _ in range(4):
        p1.build_house(med)
        p1.build_house(baltic)
    assert game.houses[med.position] == 4
    # Hotel attempt with 4 houses on med succeeds.
    cash_before = p1.cash
    available_houses_before = game.available_houses
    assert p1.build_hotel(med) is True
    assert game.hotels[med.position] is True
    assert game.houses[med.position] == 0  # 4 houses returned
    assert game.available_houses == available_houses_before + 4
    assert game.available_hotels == 11
    assert p1.cash == cash_before - med.house_cost


def test_hotel_requires_house_cost(setup):
    """Hotel costs the same as one house (returning the four to the bank)."""
    game, p1, _, _ = setup
    med, baltic = assign_group(game, p1, "brown")
    for _ in range(4):
        p1.build_house(med)
        p1.build_house(baltic)
    p1.cash = 25  # less than $50 house_cost
    assert p1.build_hotel(med) is False
    assert game.hotels[med.position] is False
    assert game.available_hotels == 12


def test_cannot_build_house_on_property_with_hotel(setup):
    """Once a hotel is up, no further houses can be added to the tile."""
    game, p1, _, _ = setup
    med, baltic = assign_group(game, p1, "brown")
    for _ in range(4):
        p1.build_house(med)
        p1.build_house(baltic)
    p1.build_hotel(med)
    assert p1.build_house(med) is False


# --- selling -----------------------------------------------------------------


def test_sell_house_returns_half_price(setup):
    """Per Hasbro rules: selling a house returns half its cost."""
    game, p1, _, _ = setup
    med, baltic = assign_group(game, p1, "brown")
    p1.build_house(med)
    p1.build_house(baltic)
    cash_before = p1.cash
    assert p1.sell_house(med) is True
    assert p1.cash == cash_before + med.house_cost // 2  # $25
    assert game.houses[med.position] == 0
    assert game.available_houses == 31  # 32 - 1 (baltic still has one)


def test_sell_hotel_requires_four_houses_in_bank(setup):
    """Per Hasbro rules: downgrading a hotel needs 4 houses in inventory."""
    game, p1, _, _ = setup
    med, baltic = assign_group(game, p1, "brown")
    for _ in range(4):
        p1.build_house(med)
        p1.build_house(baltic)
    p1.build_hotel(med)
    p1.build_hotel(baltic)
    # Drain bank inventory of houses below 4.
    game.available_houses = 3
    assert p1.sell_hotel(med) is False
    game.available_houses = 4
    cash_before = p1.cash
    assert p1.sell_hotel(med) is True
    assert game.hotels[med.position] is False
    assert game.houses[med.position] == 4
    assert game.available_houses == 0
    assert game.available_hotels == 11  # had 10 before sell, now 11
    assert p1.cash == cash_before + med.house_cost // 2


# --- bank inventory ----------------------------------------------------------


def test_bank_inventory_starts_at_thirty_two_and_twelve(setup):
    """Per Hasbro rules: 32 houses and 12 hotels in the bank initially."""
    game, _, _, _ = setup
    assert game.get_available_houses() == 32
    assert game.get_available_hotels() == 12


def test_inventory_empty_blocks_construction(setup):
    """Building when inventory is exhausted fails silently (returns False)."""
    game, p1, _, _ = setup
    assign_group(game, p1, "brown")
    game.available_houses = 0
    assert p1.build_house(game.board.tiles[1]) is False


def test_hotel_inventory_empty_blocks(setup):
    game, p1, _, _ = setup
    med, baltic = assign_group(game, p1, "brown")
    for _ in range(4):
        p1.build_house(med)
        p1.build_house(baltic)
    game.available_hotels = 0
    assert p1.build_hotel(med) is False


# --- mortgage interaction ----------------------------------------------------


def test_cannot_build_if_any_in_group_is_mortgaged(setup):
    """No buildings on a group with any mortgaged property."""
    game, p1, _, _ = setup
    med, baltic = assign_group(game, p1, "brown")
    p1.mortgage(baltic)
    assert p1.build_house(med) is False


# --- property-based invariants ----------------------------------------------


@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(min_value=0, max_value=10_000))
def test_invariant_bank_inventory_sums_to_constants(seed: int):
    """Invariant: available + in_play == 32 (houses) and 12 (hotels), always.

    A randomized sequence of build/sell operations cannot break this
    relation because every change is paired (decrement bank ↔ place on
    tile, and vice versa).
    """
    board = Board.default()
    p1 = Player("P1", cash=100_000)
    game = Game([p1], board, seed=seed)
    # Give player every street so they can build freely.
    for tile in board.tiles:
        if tile.type == "street":
            p1.properties.append(tile)
            game.owners[tile.position] = p1
    rng = game.rng
    streets = [t for t in board.tiles if t.type == "street"]
    for _ in range(120):
        tile = streets[int(rng.integers(0, len(streets)))]
        action = rng.integers(0, 4)
        if action == 0:
            p1.build_house(tile)
        elif action == 1:
            p1.build_hotel(tile)
        elif action == 2:
            p1.sell_house(tile)
        else:
            p1.sell_hotel(tile)
        houses_in_play = sum(game.houses.values())
        hotels_in_play = sum(1 for v in game.hotels.values() if v)
        assert game.available_houses + houses_in_play == 32
        assert game.available_hotels + hotels_in_play == 12


@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(min_value=0, max_value=10_000))
def test_invariant_uniformity_within_each_monopoly(seed: int):
    """Invariant: in any group the building max - min is always <= 1.

    The build / sell guards explicitly enforce uniformity, so a fuzzed
    sequence of valid (silent-fail-on-invalid) operations should never
    produce a violation.
    """
    board = Board.default()
    p1 = Player("P1", cash=100_000)
    game = Game([p1], board, seed=seed)
    for tile in board.tiles:
        if tile.type == "street":
            p1.properties.append(tile)
            game.owners[tile.position] = p1
    rng = game.rng
    streets = [t for t in board.tiles if t.type == "street"]
    for _ in range(120):
        tile = streets[int(rng.integers(0, len(streets)))]
        action = rng.integers(0, 4)
        if action == 0:
            p1.build_house(tile)
        elif action == 1:
            p1.build_hotel(tile)
        elif action == 2:
            p1.sell_house(tile)
        else:
            p1.sell_hotel(tile)
    for color, group in board.color_groups.items():
        levels = [game._building_count(t) for t in group]
        assert max(levels) - min(levels) <= 1, (
            f"Uniformity violated on {color}: {levels}"
        )
