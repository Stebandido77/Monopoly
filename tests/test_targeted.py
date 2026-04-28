"""Tests for :class:`monopoly.strategies.TargetedStrategy`."""

from __future__ import annotations

import pytest

from monopoly.board import Board, Tile
from monopoly.game import Game
from monopoly.player import Player
from monopoly.strategies.targeted import (
    PREMIUM_GROUPS,
    PURCHASE_BUFFER,
    TargetedStrategy,
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


def assign_group(game: Game, player: Player, color: str) -> list[Tile]:
    tiles = list(game.board.color_groups[color])
    for t in tiles:
        assign(game, player, t)
    return tiles


# --- decide_purchase --------------------------------------------------------


@pytest.mark.parametrize("color", sorted(PREMIUM_GROUPS))
def test_purchase_premium_group_with_buffer(setup, color):
    game, p, board = setup
    tile = next(t for t in board.tiles if t.color_group == color)
    p.cash = tile.price + PURCHASE_BUFFER + 1
    assert TargetedStrategy().decide_purchase(p, tile, game) is True


@pytest.mark.parametrize("color", ["brown", "light_blue", "pink", "green", "dark_blue"])
def test_purchase_declined_outside_premium_groups(setup, color):
    game, p, board = setup
    tile = next(t for t in board.tiles if t.color_group == color)
    p.cash = 100_000  # plenty of cash
    assert TargetedStrategy().decide_purchase(p, tile, game) is False


def test_purchase_railroad_declined(setup):
    """Railroads are not in PREMIUM_GROUPS (color_group is None)."""
    game, p, board = setup
    rr = board.tiles_by_type["railroad"][0]
    p.cash = 1000
    assert TargetedStrategy().decide_purchase(p, rr, game) is False


def test_purchase_premium_with_insufficient_buffer(setup):
    """Even premium tiles need cash > price + 100 (strict)."""
    game, p, board = setup
    orange_tile = next(t for t in board.tiles if t.color_group == "orange")
    p.cash = orange_tile.price + PURCHASE_BUFFER  # exactly the threshold
    assert TargetedStrategy().decide_purchase(p, orange_tile, game) is False


# --- decide_build -----------------------------------------------------------


def test_build_only_on_premium_monopolies(setup):
    """A monopoly on brown must NOT trigger building."""
    game, p, _ = setup
    assign_group(game, p, "brown")
    p.cash = 10_000
    assert TargetedStrategy().decide_build(p, game) == []


def test_build_aggressive_on_orange_monopoly(setup):
    """With orange monopoly + cash, builds at the AggressiveStrategy rate."""
    game, p, _ = setup
    assign_group(game, p, "orange")  # 3 tiles
    p.cash = 10_000  # plenty for 5 builds × 3 tiles × $100 = $1500
    out = TargetedStrategy().decide_build(p, game)
    # Three orange tiles each upgraded 0 → hotel = 5 build steps × 3 tiles = 15.
    assert len(out) == 15


def test_build_only_premium_when_owning_multiple_monopolies(setup):
    """Owning brown AND orange: only orange yields builds."""
    game, p, _ = setup
    assign_group(game, p, "brown")
    orange = assign_group(game, p, "orange")
    p.cash = 10_000
    out = TargetedStrategy().decide_build(p, game)
    # Every entry is from the orange group.
    assert all(t in orange for t in out)


# --- decide_jail / mortgage / unmortgage / inherited delegate to Cautious ---


def test_jail_action_matches_cautious(setup):
    """Jail policy is delegated to CautiousStrategy."""
    from monopoly.strategies.cautious import CautiousStrategy
    game, p, _ = setup
    p.cash = 1000
    assert (
        TargetedStrategy().decide_jail_action(p, game)
        == CautiousStrategy().decide_jail_action(p, game)
    )


def test_inherited_keeps_mortgaged(setup):
    game, p, board = setup
    med = board.tiles[1]
    p.cash = 100_000
    assert (
        TargetedStrategy().decide_inherited_mortgage(p, med, game)
        == "keep_mortgaged"
    )
