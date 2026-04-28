"""Tests for :class:`monopoly.strategies.AggressiveStrategy`."""

from __future__ import annotations

import pytest

from monopoly.board import Board, Tile
from monopoly.game import Game
from monopoly.player import Player
from monopoly.strategies.aggressive import AggressiveStrategy


@pytest.fixture
def setup() -> tuple[Game, Player, Board]:
    board = Board.default()
    p = Player("P", cash=2000)
    game = Game([p], board, seed=0)
    return game, p, board


def assign(game: Game, player: Player, tile: Tile) -> None:
    player.properties.append(tile)
    game.owners[tile.position] = player


def assign_group(game: Game, player: Player, color: str) -> list[Tile]:
    tiles = list(game.board.color_groups[color])
    for t in tiles:
        assign(game, player, t)
    return tiles


# --- decide_purchase --------------------------------------------------------


def test_purchase_buys_when_cash_equals_price(setup):
    """Spec: 'compra todo lo que pueda pagar (cash >= price)'."""
    game, p, board = setup
    med = board.tiles[1]  # price 60
    p.cash = 60
    assert AggressiveStrategy().decide_purchase(p, med, game) is True


def test_purchase_declines_when_cash_below_price(setup):
    game, p, board = setup
    med = board.tiles[1]
    p.cash = 59
    assert AggressiveStrategy().decide_purchase(p, med, game) is False


# --- decide_jail_action -----------------------------------------------------


def test_jail_action_always_pay(setup):
    """Spec: 'paga fianza siempre'. Engine downgrades to roll if cash < 50."""
    game, p, _ = setup
    p.cash = 5000
    assert AggressiveStrategy().decide_jail_action(p, game) == "pay"
    p.cash = 10
    # Strategy still returns "pay"; the engine handles the cash check.
    assert AggressiveStrategy().decide_jail_action(p, game) == "pay"


# --- decide_build -----------------------------------------------------------


def test_build_returns_empty_without_monopoly(setup):
    game, p, _ = setup
    assign(game, p, game.board.tiles[1])
    assert AggressiveStrategy().decide_build(p, game) == []


def test_build_maxes_out_brown_with_ample_cash(setup):
    """With $10000 P should fill brown to two hotels (4*4 = 8 houses, then 2 hotels)."""
    game, p, _ = setup
    assign_group(game, p, "brown")
    p.cash = 10_000
    out = AggressiveStrategy().decide_build(p, game)
    # Brown house_cost=$50. To go 0 → hotel on each of two tiles is
    # 5 builds * 2 tiles * $50 = $500 total.
    assert len(out) == 10  # 4 houses each + 1 hotel each = 10 build steps
    # Final state simulated: both tiles have a hotel — 2 hotel steps end the list.
    # Order of last two builds doesn't matter (round-robin).


def test_build_round_robin_starts_with_lowest_count(setup):
    """First build picks the lowest-count tile."""
    game, p, _ = setup
    tiles = assign_group(game, p, "brown")
    p.cash = 10_000
    p.build_house(tiles[0])  # state (1, 0) for med, baltic
    p.cash = 10_000
    out = AggressiveStrategy().decide_build(p, game)
    # First entry must be tiles[1] (Baltic, count 0) — uniformity demands it.
    assert out[0] is tiles[1]


def test_build_stops_at_cash_zero(setup):
    """Stops when next build would push cash negative."""
    game, p, _ = setup
    assign_group(game, p, "brown")
    p.cash = 100  # exactly two builds (at $50 each); third would go to -50
    out = AggressiveStrategy().decide_build(p, game)
    assert len(out) == 2


def test_build_skips_mortgaged_group(setup):
    game, p, _ = setup
    tiles = assign_group(game, p, "brown")
    p.mortgage(tiles[0])
    p.cash = 10_000
    assert AggressiveStrategy().decide_build(p, game) == []


# --- decide_mortgage --------------------------------------------------------


def test_mortgage_skips_when_solvent(setup):
    """Spec: 'hipoteca solo si va a quebrar (cash < 0)'."""
    game, p, board = setup
    assign(game, p, board.tiles[1])
    p.cash = 0
    assert AggressiveStrategy().decide_mortgage(p, game) == []


def test_mortgage_lists_unmortgaged_when_negative(setup):
    game, p, board = setup
    med = board.tiles[1]
    rr = board.tiles[5]
    for t in (med, rr):
        assign(game, p, t)
    p.cash = -10
    out = AggressiveStrategy().decide_mortgage(p, game)
    assert set(out) == {med, rr}


def test_mortgage_skips_already_mortgaged(setup):
    game, p, board = setup
    med = board.tiles[1]
    assign(game, p, med)
    p.mortgage(med)
    p.cash = -10
    assert AggressiveStrategy().decide_mortgage(p, game) == []


# --- decide_unmortgage ------------------------------------------------------


def test_unmortgage_never(setup):
    """Spec: 'nunca (mantiene capital activo)'."""
    game, p, board = setup
    med = board.tiles[1]
    assign(game, p, med)
    p.mortgage(med)
    p.cash = 1_000_000
    assert AggressiveStrategy().decide_unmortgage(p, game) == []


# --- decide_inherited_mortgage ----------------------------------------------


def test_inherited_unmortgage_when_rich(setup):
    """Spec: '"unmortgage" si cash >= mortgage_value × 1.10'."""
    game, p, board = setup
    med = board.tiles[1]  # mortgage_value = 30 → cost = ceil(33) = 33
    p.cash = 33
    assert (
        AggressiveStrategy().decide_inherited_mortgage(p, med, game)
        == "unmortgage"
    )


def test_inherited_keep_when_short(setup):
    game, p, board = setup
    med = board.tiles[1]  # cost 33
    p.cash = 32
    assert (
        AggressiveStrategy().decide_inherited_mortgage(p, med, game)
        == "keep_mortgaged"
    )
