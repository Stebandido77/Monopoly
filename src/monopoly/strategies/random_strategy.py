"""Minimal baseline strategy used as a smoke-test driver.

Despite the name, :class:`RandomStrategy` is currently deterministic: it
always purchases when affordable and always rolls to escape jail. The name
is reserved for the eventual randomized variant; for now it is the
"always-buy" baseline against which other strategies will be benchmarked.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from monopoly.strategies.base import JailAction

if TYPE_CHECKING:
    from monopoly.board import Tile
    from monopoly.game import Game
    from monopoly.player import Player


class RandomStrategy:
    """Always buys when offered; always attempts to roll out of jail."""

    def decide_purchase(
        self, player: Player, tile: Tile, game_state: Game
    ) -> bool:
        return True

    def decide_jail_action(
        self, player: Player, game_state: Game
    ) -> JailAction:
        return "roll"
