"""RandomAggressiveStrategy: like RandomStrategy but builds at p=0.5.

A more active baseline than :class:`monopoly.strategies.RandomStrategy`.
Useful as a benchmark partner because the higher build probability
produces more late-game rent and faster terminal states, which exercises
the bankruptcy / management paths in benchmark runs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from monopoly.strategies.base import JailAction

if TYPE_CHECKING:
    from monopoly.board import Tile
    from monopoly.game import Game
    from monopoly.player import Player


BUILD_PROBABILITY = 0.5


class RandomAggressiveStrategy:
    """Always buys; always rolls; builds with p=0.5 on each monopoly tile."""

    def decide_purchase(
        self, player: Player, tile: Tile, game_state: Game
    ) -> bool:
        return True

    def decide_jail_action(self, player: Player, game_state: Game) -> JailAction:
        return "roll"

    def decide_build(self, player: Player, game_state: Game) -> list[Tile]:
        chosen: list[Tile] = []
        for _color, group in game_state.board.color_groups.items():
            if not all(game_state.owners[t.position] is player for t in group):
                continue
            for tile in group:
                if tile.house_cost is None:
                    continue
                if player.cash <= tile.house_cost * 2:
                    continue
                if game_state.rng.random() < BUILD_PROBABILITY:
                    chosen.append(tile)
        return chosen
