"""Minimal baseline strategy used as a smoke-test driver.

Despite the name, :class:`RandomStrategy` is mostly deterministic: it always
purchases when affordable and always rolls to escape jail. The one
randomized hook is :meth:`decide_build` — when the player owns a complete
monopoly and has cash exceeding twice the house cost, each property is
independently selected for one build with probability 0.3, using the game's
RNG. This keeps the strategy reproducible under a fixed seed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from monopoly.strategies.base import JailAction

if TYPE_CHECKING:
    from monopoly.board import Tile
    from monopoly.game import Game
    from monopoly.player import Player


class RandomStrategy:
    """Always buys; always rolls out of jail; randomly builds on monopolies."""

    def decide_purchase(
        self, player: Player, tile: Tile, game_state: Game
    ) -> bool:
        return True

    def decide_jail_action(
        self, player: Player, game_state: Game
    ) -> JailAction:
        return "roll"

    def decide_build(self, player: Player, game_state: Game) -> list[Tile]:
        """Pick monopoly properties to build on, each with p=0.3 if cash allows."""
        chosen: list[Tile] = []
        for _color, group in game_state.board.color_groups.items():
            if not all(game_state.owners[t.position] is player for t in group):
                continue
            for tile in group:
                if tile.house_cost is None:
                    continue
                if player.cash <= tile.house_cost * 2:
                    continue
                if game_state.rng.random() < 0.3:
                    chosen.append(tile)
        return chosen
