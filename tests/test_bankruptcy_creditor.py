"""Tests for bankruptcy with a creditor (Phase 2, Part E).

When the debt is owed to another player, the debtor's holdings transfer to
the creditor: properties (with mortgage flag preserved), houses and hotels
sold to the bank at half price (cash to the creditor), and any held
Get-Out-of-Jail-Free cards are returned to their decks. Inherited
mortgaged properties trigger the creditor's
``Strategy.decide_inherited_mortgage`` hook (default ``"keep_mortgaged"``).

When the debt is to the bank, ADR-003 applies: properties revert to the
bank, no auction, buildings return to inventory, mortgage flags clear.
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


def assign_brown(game: Game, player: Player) -> tuple[Tile, Tile]:
    med = game.board.tiles[1]
    baltic = game.board.tiles[3]
    assign(game, player, med)
    assign(game, player, baltic)
    return med, baltic


# --- bank case (ADR-003) ----------------------------------------------------


def test_bank_bankruptcy_returns_buildings_to_inventory(setup):
    game, p1, _, board = setup
    med, baltic = assign_brown(game, p1)
    p1.build_house(med)
    p1.build_house(baltic)
    p1.build_house(med)  # state (2, 1), 3 houses out
    assert game.available_houses == 32 - 3
    p1.cash = -10
    assert game.check_bankruptcy(p1) is True
    assert game.available_houses == 32
    assert game.houses[med.position] == 0
    assert game.houses[baltic.position] == 0
    assert game.owners[med.position] is None
    assert game.owners[baltic.position] is None


def test_bank_bankruptcy_clears_mortgage_flag(setup):
    game, p1, _, _ = setup
    med, _ = assign_brown(game, p1)
    p1.mortgage(med)
    p1.cash = -100
    game.check_bankruptcy(p1)
    assert game.mortgaged[med.position] is False


# --- creditor case ----------------------------------------------------------


def test_creditor_inherits_unmortgaged_properties(setup):
    game, p1, p2, _ = setup
    med, baltic = assign_brown(game, p1)
    p1.cash = -50
    assert game.check_bankruptcy(p1, creditor=p2) is True
    assert game.owners[med.position] is p2
    assert game.owners[baltic.position] is p2
    assert med in p2.properties and baltic in p2.properties
    assert p1.properties == []


def test_creditor_receives_half_value_for_buildings(setup):
    """Per Hasbro rules: houses and hotels are sold to the bank at half price.

    The cash goes to the creditor; the buildings return to the bank
    inventory.
    """
    game, p1, p2, _ = setup
    med, baltic = assign_brown(game, p1)
    p1.build_house(med)
    p1.build_house(baltic)  # state (1, 1) — two houses out, $50 each
    p1.cash = -10
    cash_before_p2 = p2.cash
    game.check_bankruptcy(p1, creditor=p2)
    # Two houses × $25 each = $50 to creditor.
    assert p2.cash == cash_before_p2 + 2 * (med.house_cost // 2)
    assert game.available_houses == 32  # both houses returned
    assert game.houses[med.position] == 0
    assert game.houses[baltic.position] == 0


def test_creditor_receives_half_value_for_hotel(setup):
    game, p1, p2, _ = setup
    med, baltic = assign_brown(game, p1)
    for _ in range(4):
        p1.build_house(med)
        p1.build_house(baltic)
    p1.build_hotel(med)  # 1 hotel + 4 houses on baltic in play
    available_houses_before = game.available_houses
    available_hotels_before = game.available_hotels
    p1.cash = -10
    cash_before_p2 = p2.cash
    game.check_bankruptcy(p1, creditor=p2)
    # 4 houses × $25 + 1 hotel × $25 = $125 to creditor.
    assert p2.cash == cash_before_p2 + 5 * (med.house_cost // 2)
    assert game.available_houses == available_houses_before + 4
    assert game.available_hotels == available_hotels_before + 1
    assert game.hotels[med.position] is False


def test_creditor_default_keep_mortgaged_pays_ten_percent(setup):
    """Default decision: pay 10% of mortgage_value to keep the property mortgaged."""
    game, p1, p2, _ = setup
    med, baltic = assign_brown(game, p1)
    p1.mortgage(med)  # mortgage_value=30
    p1.mortgage(baltic)
    p1.cash = -10
    cash_before_p2 = p2.cash
    game.check_bankruptcy(p1, creditor=p2)
    # No strategy registered → default 'keep_mortgaged' → pay $3 each (10% of 30).
    expected_fees = math.ceil(30 * 0.10) * 2
    assert p2.cash == cash_before_p2 - expected_fees
    assert game.mortgaged[med.position] is True
    assert game.mortgaged[baltic.position] is True
    assert game.owners[med.position] is p2


def test_creditor_can_choose_to_unmortgage_via_strategy(setup):
    """A strategy returning 'unmortgage' pays the full 110% to lift each lien."""
    game, p1, p2, _ = setup

    class EagerCreditor:
        def decide_purchase(self, player, tile, game_state):
            return False

        def decide_jail_action(self, player, game_state):
            return "roll"

        def decide_inherited_mortgage(self, player, tile, game_state):
            return "unmortgage"

    game.strategies["P2"] = EagerCreditor()
    med, _ = assign_brown(game, p1)
    p1.mortgage(med)  # mortgage_value=30
    p1.cash = -10
    p2.cash = 1000
    game.check_bankruptcy(p1, creditor=p2)
    # 110% of 30 = 33.
    assert p2.cash == 1000 - 33
    assert game.mortgaged[med.position] is False


def test_creditor_inherits_held_jail_cards_returned_to_decks(setup):
    """Held Get-Out-of-Jail-Free cards return to their origin decks on bankruptcy."""
    from monopoly.cards import Card

    game, p1, p2, _ = setup
    held = Card("GoJF", "get_out_of_jail", {"deck": "chance"})
    p1.jail_free_cards.append(held)
    chance_size_before = len(game.chance_deck)
    p1.cash = -10
    game.check_bankruptcy(p1, creditor=p2)
    assert p1.jail_free_cards == []
    assert len(game.chance_deck) == chance_size_before + 1


# --- end-to-end via pay_rent -------------------------------------------------


def test_rent_drives_bankruptcy_with_creditor_via_resolve(setup):
    """A failed rent payment routes properties to the rent owner."""
    game, p1, p2, _ = setup
    rrs = game.board.tiles_by_type["railroad"]
    for r in rrs:
        assign(game, p2, r)  # P2 owns all 4 railroads → $200 rent
    p1.cash = 100
    # P1 lands on a P2-owned railroad and goes bankrupt.
    p1.position = rrs[0].position
    game._resolve_landing(p1, rrs[0], dice_roll=0)
    assert p1.cash < 0
    # Properties of P1 (none here) would have transferred; the cash is with P2.
    assert p2.cash == 2000 + 200
    # Bankruptcy was processed: P1 has nothing.
    assert p1.properties == []
