"""Tests for :class:`monopoly.strategies.CautiousStrategy`.

Each test sets up a Game and force-assigns properties to bypass the
strategy-driven purchase loop, then asserts the strategy's decision
matches the spec exactly at the threshold and just past it.
"""

from __future__ import annotations

import pytest

from monopoly.board import Board, Tile
from monopoly.game import Game
from monopoly.player import Player
from monopoly.strategies.cautious import (
    JAIL_PAY_THRESHOLD,
    MIN_CASH_AFTER_BUILD,
    MORTGAGE_THRESHOLD,
    PURCHASE_BUFFER,
    UNMORTGAGE_THRESHOLD,
    CautiousStrategy,
)


@pytest.fixture
def setup() -> tuple[Game, Player, Board]:
    board = Board.default()
    p = Player("P", cash=2000)
    game = Game([p], board, seed=0)
    return game, p, board


def assign(game: Game, player: Player, tile: Tile) -> None:
    player.properties.append(tile)
    game.owners[tile.position] = player


# --- decide_purchase --------------------------------------------------------


def test_purchase_buys_above_buffer(setup):
    game, p, board = setup
    med = board.tiles[1]  # price 60
    p.cash = 60 + PURCHASE_BUFFER + 1  # exactly one past the threshold
    assert CautiousStrategy().decide_purchase(p, med, game) is True


def test_purchase_declines_at_buffer(setup):
    """Strict inequality: cash > price + buffer (equality must decline)."""
    game, p, board = setup
    med = board.tiles[1]
    p.cash = 60 + PURCHASE_BUFFER  # exactly the threshold
    assert CautiousStrategy().decide_purchase(p, med, game) is False


def test_purchase_declines_below_buffer(setup):
    game, p, board = setup
    med = board.tiles[1]
    p.cash = 60 + PURCHASE_BUFFER - 1
    assert CautiousStrategy().decide_purchase(p, med, game) is False


# --- decide_jail_action -----------------------------------------------------


def test_jail_uses_card_when_available(setup):
    from monopoly.cards import Card
    game, p, _ = setup
    p.jail_free_cards.append(Card("GoJF", "get_out_of_jail", {"deck": "chance"}))
    assert CautiousStrategy().decide_jail_action(p, game) == "card"


def test_jail_pays_when_cash_above_threshold(setup):
    game, p, _ = setup
    p.cash = JAIL_PAY_THRESHOLD + 1
    assert CautiousStrategy().decide_jail_action(p, game) == "pay"


def test_jail_rolls_when_cash_at_threshold(setup):
    """Strict inequality: cash > 500 to pay."""
    game, p, _ = setup
    p.cash = JAIL_PAY_THRESHOLD
    assert CautiousStrategy().decide_jail_action(p, game) == "roll"


def test_jail_rolls_when_low_cash(setup):
    game, p, _ = setup
    p.cash = 30
    assert CautiousStrategy().decide_jail_action(p, game) == "roll"


# --- decide_build -----------------------------------------------------------


def test_build_returns_empty_without_monopoly(setup):
    game, p, board = setup
    assign(game, p, board.tiles[1])  # only Mediterranean
    assert CautiousStrategy().decide_build(p, game) == []


def test_build_returns_one_tile_with_monopoly(setup):
    """One construction per turn — the list has exactly one element."""
    game, p, board = setup
    med = board.tiles[1]
    baltic = board.tiles[3]
    assign(game, p, med)
    assign(game, p, baltic)
    p.cash = 600  # 600 - 50 = 550 > 500 → eligible
    out = CautiousStrategy().decide_build(p, game)
    assert len(out) == 1
    assert out[0].color_group == "brown"


def test_build_skips_when_post_build_cash_at_threshold(setup):
    """Strict inequality: cash - cost > MIN_CASH_AFTER_BUILD."""
    game, p, board = setup
    med = board.tiles[1]
    baltic = board.tiles[3]
    assign(game, p, med)
    assign(game, p, baltic)
    p.cash = MIN_CASH_AFTER_BUILD + med.house_cost  # post-build = 500 exactly
    assert CautiousStrategy().decide_build(p, game) == []


def test_build_skips_mortgaged_group(setup):
    game, p, board = setup
    med = board.tiles[1]
    baltic = board.tiles[3]
    assign(game, p, med)
    assign(game, p, baltic)
    p.mortgage(baltic)
    p.cash = 1000
    assert CautiousStrategy().decide_build(p, game) == []


def test_build_picks_lowest_count_tile(setup):
    game, p, board = setup
    med = board.tiles[1]
    baltic = board.tiles[3]
    assign(game, p, med)
    assign(game, p, baltic)
    p.cash = 600
    p.build_house(med)  # state (1, 0)
    p.cash = 600
    out = CautiousStrategy().decide_build(p, game)
    assert out == [baltic]  # baltic has 0, med has 1; picks baltic


# --- decide_mortgage --------------------------------------------------------


def test_mortgage_skips_when_cash_above_threshold(setup):
    game, p, board = setup
    assign(game, p, board.tiles[1])
    p.cash = MORTGAGE_THRESHOLD
    assert CautiousStrategy().decide_mortgage(p, game) == []


def test_mortgage_orders_non_monopoly_first(setup):
    """Spec: 'eligiendo primero propiedades de grupos sin monopolio'."""
    game, p, board = setup
    # P owns Mediterranean only (not full brown) and Connecticut only (not full
    # light_blue) — both non-monopoly; and the entire orange group (monopoly).
    med = board.tiles[1]
    conn = board.tiles[9]
    orange_tiles = list(board.color_groups["orange"])
    assign(game, p, med)
    assign(game, p, conn)
    for t in orange_tiles:
        assign(game, p, t)
    p.cash = 50  # below threshold
    out = CautiousStrategy().decide_mortgage(p, game)
    # First two entries must be non-monopoly tiles (med and conn, in some order).
    non_mono = {med, conn}
    assert set(out[:2]) == non_mono
    # Followed by orange tiles.
    assert set(out[2:]) == set(orange_tiles)


def test_mortgage_skips_already_mortgaged(setup):
    game, p, board = setup
    med = board.tiles[1]
    assign(game, p, med)
    p.mortgage(med)
    p.cash = 50
    assert CautiousStrategy().decide_mortgage(p, game) == []


# --- decide_unmortgage ------------------------------------------------------


def test_unmortgage_skips_at_threshold(setup):
    """Strict inequality: cash > UNMORTGAGE_THRESHOLD."""
    game, p, board = setup
    med = board.tiles[1]
    assign(game, p, med)
    p.mortgage(med)
    p.cash = UNMORTGAGE_THRESHOLD
    assert CautiousStrategy().decide_unmortgage(p, game) == []


def test_unmortgage_returns_mortgaged_when_rich(setup):
    game, p, board = setup
    med = board.tiles[1]
    baltic = board.tiles[3]
    for t in (med, baltic):
        assign(game, p, t)
    p.mortgage(med)
    p.mortgage(baltic)
    p.cash = UNMORTGAGE_THRESHOLD + 1000
    out = CautiousStrategy().decide_unmortgage(p, game)
    assert set(out) == {med, baltic}


# --- decide_inherited_mortgage ----------------------------------------------


def test_inherited_mortgage_always_keeps(setup):
    game, p, board = setup
    med = board.tiles[1]
    p.cash = 100_000  # plenty
    assert (
        CautiousStrategy().decide_inherited_mortgage(p, med, game)
        == "keep_mortgaged"
    )
