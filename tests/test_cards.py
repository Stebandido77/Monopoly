"""Tests for the Card / Deck primitives and card-effect application.

The deck integration tests stage a deterministic deck (a single card,
unshuffled effectively) so each card effect can be exercised without
worrying about which card the RNG happens to deal first.
"""

from __future__ import annotations

import numpy as np

from monopoly.board import Board
from monopoly.cards import (
    Card,
    Deck,
    default_chance_path,
    default_community_chest_path,
    load_cards,
)
from monopoly.game import Game
from monopoly.player import Player

# --- primitives --------------------------------------------------------------


def test_deck_draw_then_return_rotates_to_bottom():
    rng = np.random.default_rng(0)
    a = Card("A", "collect", {"amount": 1})
    b = Card("B", "pay", {"amount": 2})
    c = Card("C", "go_to_jail")
    deck = Deck([a, b, c], rng)
    drawn = deck.draw()
    assert len(deck) == 2
    deck.return_card(drawn)
    assert len(deck) == 3
    # The returned card is at the bottom now.
    assert deck.cards[-1] is drawn


def test_deck_initial_shuffle_is_seed_deterministic():
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    cards = [Card(str(i), "collect", {"amount": i}) for i in range(16)]
    d1 = Deck(list(cards), rng1)
    d2 = Deck(list(cards), rng2)
    assert [c.name for c in d1.cards] == [c.name for c in d2.cards]


def test_load_chance_yaml_has_sixteen_cards():
    cards = load_cards(default_chance_path())
    assert len(cards) == 16


def test_load_community_chest_yaml_has_sixteen_cards():
    cards = load_cards(default_community_chest_path())
    assert len(cards) == 16


# --- card effects via Game.draw_card with a stacked deck ---------------------


def make_game(card: Card, deck_kind: str = "chance") -> tuple[Game, Player, Player, Board]:
    """Build a Game where the next draw on ``deck_kind`` returns ``card``."""
    board = Board.default()
    p1 = Player("P1", cash=2000)
    p2 = Player("P2", cash=2000)
    rng = np.random.default_rng(0)
    if deck_kind == "chance":
        chance = Deck([card], rng)
        cc = Deck(load_cards(default_community_chest_path()), rng)
    else:
        chance = Deck(load_cards(default_chance_path()), rng)
        cc = Deck([card], rng)
    game = Game(
        [p1, p2],
        board,
        seed=0,
        chance_deck=chance,
        community_chest_deck=cc,
    )
    return game, p1, p2, board


def test_collect_card_credits_player(make_game=make_game):
    card = Card("Bank dividend", "collect", {"amount": 50})
    game, p1, _, _ = make_game(card)
    cash_before = p1.cash
    game.draw_card("chance", p1)
    assert p1.cash == cash_before + 50
    # Card returned to deck (not get_out_of_jail).
    assert len(game.chance_deck) == 1


def test_pay_card_debits_player(make_game=make_game):
    card = Card("Speeding fine", "pay", {"amount": 15})
    game, p1, _, _ = make_game(card)
    cash_before = p1.cash
    game.draw_card("chance", p1)
    assert p1.cash == cash_before - 15


def test_move_to_position_pays_go_when_crossing(make_game=make_game):
    """Advance to Go from position 30 → +$200 salary, then resolve at GO."""
    card = Card("Advance to Go", "move_to_position", {"position": 0, "pass_go": True})
    game, p1, _, _ = make_game(card)
    p1.position = 30
    cash_before = p1.cash
    game.draw_card("chance", p1)
    assert p1.position == 0
    assert p1.cash == cash_before + 200


def test_move_to_position_no_pass_go(make_game=make_game):
    """Take a walk on the Boardwalk does NOT pay GO salary."""
    card = Card(
        "Take a walk on the Boardwalk", "move_to_position", {"position": 39, "pass_go": False}
    )
    game, p1, _, _ = make_game(card)
    p1.position = 5  # forward to 39, would not wrap anyway, but check flag respect
    cash_before = p1.cash
    game.draw_card("chance", p1)
    assert p1.position == 39
    assert p1.cash == cash_before


def test_move_to_nearest_railroad_finds_clockwise(make_game=make_game):
    card = Card(
        "Advance to nearest Railroad",
        "move_to_nearest",
        {"target_type": "railroad", "pay_owner_double": True},
    )
    game, p1, _, _ = make_game(card)
    p1.position = 8  # nearest RR clockwise is Pennsylvania at 15
    game.draw_card("chance", p1)
    assert p1.position == 15


def test_move_to_nearest_railroad_pays_double_when_owned(make_game=make_game):
    """Pay 2× the normal rent when nearest railroad is owned by another."""
    card = Card(
        "Advance to nearest Railroad",
        "move_to_nearest",
        {"target_type": "railroad", "pay_owner_double": True},
    )
    game, p1, p2, _ = make_game(card)
    rrs = game.board.tiles_by_type["railroad"]
    # P2 owns one railroad → normal rent is $25, doubled to $50.
    p2.properties.append(rrs[2])  # B&O at 25
    game.owners[rrs[2].position] = p2
    p1.position = 23  # nearest forward RR is B&O (25)
    cash_before_p1 = p1.cash
    cash_before_p2 = p2.cash
    game.draw_card("chance", p1)
    assert p1.position == 25
    assert p1.cash == cash_before_p1 - 50
    assert p2.cash == cash_before_p2 + 50


def test_move_relative_minus_three(make_game=make_game):
    """Go Back 3 Spaces from position 36 (Chance) lands on 33 (Community Chest)."""
    card = Card("Go Back 3 Spaces", "move_relative", {"offset": -3})
    game, p1, _, _ = make_game(card)
    p1.position = 36
    game.draw_card("chance", p1)
    # We landed on tile 33 — Community Chest. The engine recursively draws a CC
    # card. We don't assert on the CC card outcome here (deck content varies);
    # we only verify the position change is correct.
    assert p1.position == 33


def test_collect_from_each_player(make_game=make_game):
    card = Card("Birthday", "collect_from_each_player", {"amount": 10})
    game, p1, p2, _ = make_game(card)
    game.draw_card("chance", p1)
    assert p1.cash == 2010
    assert p2.cash == 1990


def test_pay_each_player(make_game=make_game):
    card = Card("Chairman", "pay_each_player", {"amount": 50})
    game, p1, p2, _ = make_game(card)
    game.draw_card("chance", p1)
    assert p1.cash == 1950
    assert p2.cash == 2050


def test_pay_per_house_and_hotel(make_game=make_game):
    card = Card(
        "Repairs",
        "pay_per_house_and_hotel",
        {"per_house": 25, "per_hotel": 100},
    )
    game, p1, _, _ = make_game(card)
    # Force two houses on one brown tile and a hotel on another.
    med = game.board.tiles[1]
    baltic = game.board.tiles[3]
    p1.properties.extend([med, baltic])
    game.owners[med.position] = p1
    game.owners[baltic.position] = p1
    game.houses[med.position] = 2
    game.hotels[baltic.position] = True
    cash_before = p1.cash
    game.draw_card("chance", p1)
    # 2 houses × 25 + 1 hotel × 100 = 150
    assert p1.cash == cash_before - 150


def test_go_to_jail_card_sends_player_to_jail(make_game=make_game):
    card = Card("Go to Jail", "go_to_jail", {})
    game, p1, _, _ = make_game(card)
    game.draw_card("chance", p1)
    assert p1.in_jail is True
    assert p1.position == game._jail_position


def test_get_out_of_jail_card_stays_with_player(make_game=make_game):
    card = Card("GoJF", "get_out_of_jail", {"deck": "chance"})
    game, p1, _, _ = make_game(card)
    chance_size_before = len(game.chance_deck)
    game.draw_card("chance", p1)
    # Card NOT returned to deck.
    assert len(game.chance_deck) == chance_size_before - 1
    assert len(p1.jail_free_cards) == 1
    assert p1.jail_free_cards[0].effect_type == "get_out_of_jail"


def test_using_jail_card_returns_it_to_origin_deck():
    """Per ADR-001 closure: action='card' consumes the player's card."""

    class CardJailStrategy:
        def decide_purchase(self, player, tile, game_state):
            return False

        def decide_jail_action(self, player, game_state):
            return "card"

    board = Board.default()
    p = Player("P", cash=200)
    rng = np.random.default_rng(0)
    chance = Deck(load_cards(default_chance_path()), rng)
    cc = Deck(load_cards(default_community_chest_path()), rng)
    game = Game(
        [p],
        board,
        strategies={"P": CardJailStrategy()},
        seed=0,
        chance_deck=chance,
        community_chest_deck=cc,
    )
    # Hand a CC-origin card to the player and put them in jail.
    held = Card("Held GoJF", "get_out_of_jail", {"deck": "community_chest"})
    p.jail_free_cards.append(held)
    p.in_jail = True
    p.position = game._jail_position
    cc_size_before = len(game.community_chest_deck)
    game.handle_jail(p)
    # Card consumed from player and returned to community_chest deck.
    assert p.jail_free_cards == []
    assert p.in_jail is False
    assert len(game.community_chest_deck) == cc_size_before + 1


def test_action_card_without_held_card_falls_through_to_roll():
    """ADR-001: ``"card"`` with no held card behaves as ``"roll"``."""

    class CardJailStrategy:
        def decide_purchase(self, player, tile, game_state):
            return False

        def decide_jail_action(self, player, game_state):
            return "card"

    board = Board.default()
    p = Player("P", cash=200)
    rng = np.random.default_rng(0)
    chance = Deck(load_cards(default_chance_path()), rng)
    cc = Deck(load_cards(default_community_chest_path()), rng)
    game = Game(
        [p],
        board,
        strategies={"P": CardJailStrategy()},
        seed=0,
        chance_deck=chance,
        community_chest_deck=cc,
    )
    p.in_jail = True
    p.position = game._jail_position
    # Force the dice path to return non-doubles so the player stays.
    game.roll_dice = lambda: (1, 2)  # type: ignore[method-assign]
    result = game.handle_jail(p)
    assert result is None
    assert p.in_jail is True
    assert p.jail_turns == 1


# --- landing on Chance / Community Chest triggers a draw ---------------------


def test_landing_on_chance_draws_a_card():
    """A landing resolver hitting position 7 must consume a Chance card."""
    board = Board.default()
    p = Player("P", cash=2000)
    rng = np.random.default_rng(0)
    bank_card = Card("Bank dividend", "collect", {"amount": 50})
    chance = Deck([bank_card], rng)
    cc = Deck(load_cards(default_community_chest_path()), rng)
    game = Game(
        [p],
        board,
        seed=0,
        chance_deck=chance,
        community_chest_deck=cc,
    )
    cash_before = p.cash
    game._resolve_landing(p, board.tiles[7], dice_roll=0)
    assert p.cash == cash_before + 50


def test_landing_on_community_chest_draws_a_card():
    board = Board.default()
    p = Player("P", cash=2000)
    rng = np.random.default_rng(0)
    bank_err = Card("Bank error", "collect", {"amount": 200})
    chance = Deck(load_cards(default_chance_path()), rng)
    cc = Deck([bank_err], rng)
    game = Game(
        [p],
        board,
        seed=0,
        chance_deck=chance,
        community_chest_deck=cc,
    )
    cash_before = p.cash
    game._resolve_landing(p, board.tiles[2], dice_roll=0)
    assert p.cash == cash_before + 200
