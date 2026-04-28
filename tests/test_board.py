"""Tests for the static board loaded from data/board.yaml.

These tests assert the OFFICIAL Hasbro values for the standard US edition
(modern rules), not the values found in the legacy notebooks.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from monopoly.board import Board

REPO_ROOT = Path(__file__).resolve().parents[1]
BOARD_PATH = REPO_ROOT / "data" / "board.yaml"


def test_board_loads_40_tiles_in_order():
    board = Board.from_yaml(BOARD_PATH)
    assert len(board.tiles) == 40
    for i, tile in enumerate(board.tiles):
        assert tile.position == i


def test_default_loader_finds_bundled_board():
    board = Board.default()
    assert len(board.tiles) == 40


def test_color_groups_have_official_counts():
    """Brown and dark blue have 2 streets each; the other six groups have 3."""
    board = Board.default()
    assert len(board.color_groups["brown"]) == 2
    assert len(board.color_groups["dark_blue"]) == 2
    for color in ("light_blue", "pink", "orange", "red", "yellow", "green"):
        assert len(board.color_groups[color]) == 3


def test_tiles_by_type_official_counts():
    board = Board.default()
    by_type = board.tiles_by_type
    assert len(by_type["street"]) == 22
    assert len(by_type["railroad"]) == 4
    assert len(by_type["utility"]) == 2
    assert len(by_type["chance"]) == 3
    assert len(by_type["community_chest"]) == 3
    assert len(by_type["tax"]) == 2
    assert len(by_type["go"]) == 1
    assert len(by_type["jail"]) == 1
    assert len(by_type["free_parking"]) == 1
    assert len(by_type["go_to_jail"]) == 1


def test_tile_is_frozen():
    board = Board.default()
    with pytest.raises(FrozenInstanceError):
        board.tiles[0].name = "Modified"  # type: ignore[misc]


def test_mediterranean_avenue_official_values():
    """First brown street: $60 price, $2 base rent, $50/house."""
    board = Board.default()
    med = board.tiles[1]
    assert med.name == "Mediterranean Avenue"
    assert med.type == "street"
    assert med.color_group == "brown"
    assert med.price == 60
    assert med.rent == (2, 10, 30, 90, 160, 250)
    assert med.house_cost == 50
    assert med.mortgage_value == 30


def test_boardwalk_official_values():
    """Highest-value street: $400 price, $50 base rent, $200/house."""
    board = Board.default()
    bw = board.tiles[39]
    assert bw.name == "Boardwalk"
    assert bw.type == "street"
    assert bw.color_group == "dark_blue"
    assert bw.price == 400
    assert bw.rent == (50, 200, 600, 1400, 1700, 2000)
    assert bw.house_cost == 200
    assert bw.mortgage_value == 200


def test_railroad_uniform_pricing():
    """All four railroads cost $200 with rent schedule 25/50/100/200."""
    board = Board.default()
    railroads = board.tiles_by_type["railroad"]
    assert len(railroads) == 4
    for r in railroads:
        assert r.price == 200
        assert r.rent == (25, 50, 100, 200)
        assert r.mortgage_value == 100


def test_utility_rent_multipliers():
    """Utilities cost $150 and rent at 4x or 10x the dice roll."""
    board = Board.default()
    utilities = board.tiles_by_type["utility"]
    assert len(utilities) == 2
    for u in utilities:
        assert u.price == 150
        assert u.rent_multipliers == (4, 10)
        assert u.mortgage_value == 75


def test_tax_amounts():
    """Income Tax (pos 4) is $200; Luxury Tax (pos 38) is $75 in modern rules."""
    board = Board.default()
    income = board.tiles[4]
    luxury = board.tiles[38]
    assert income.name == "Income Tax"
    assert income.type == "tax"
    assert income.tax_amount == 200
    assert luxury.name == "Luxury Tax"
    assert luxury.type == "tax"
    assert luxury.tax_amount == 75


def test_bank_config_official():
    board = Board.default()
    assert board.bank.starting_money == 1500
    assert board.bank.go_salary == 200
    assert board.bank.jail_fine == 50
    assert board.bank.total_houses == 32
    assert board.bank.total_hotels == 12


def test_tile_is_property_helper():
    board = Board.default()
    assert board.tiles[0].is_property is False  # Go
    assert board.tiles[1].is_property is True  # Mediterranean (street)
    assert board.tiles[5].is_property is True  # Reading Railroad
    assert board.tiles[12].is_property is True  # Electric Company
    assert board.tiles[10].is_property is False  # Jail
    assert board.tiles[20].is_property is False  # Free Parking
    assert board.tiles[30].is_property is False  # Go to Jail
    assert board.tiles[4].is_property is False  # Income Tax
    assert board.tiles[7].is_property is False  # Chance
    assert board.tiles[2].is_property is False  # Community Chest


def test_jail_and_go_to_jail_positions():
    """Per Hasbro layout: Jail is at position 10, Go-to-Jail at 30."""
    board = Board.default()
    assert board.tiles[10].type == "jail"
    assert board.tiles[30].type == "go_to_jail"
