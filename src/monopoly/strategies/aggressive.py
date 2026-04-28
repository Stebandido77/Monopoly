"""AggressiveStrategy: maximally invested at all times.

Buys every affordable property, builds to the limit on each owned monopoly
(spending down toward $0 if needed), mortgages only when about to go
negative, never voluntarily unmortgages, and always pays the jail fine to
keep moving. Inherited mortgaged properties get cleared immediately when
cash allows.

The greedy build planner lives in :mod:`monopoly.strategies._build_plan`
so :class:`monopoly.strategies.targeted.TargetedStrategy` can reuse it
with a different monopoly filter.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from monopoly.strategies._build_plan import eligible_monopolies, greedy_build_plan
from monopoly.strategies.base import JailAction, MortgageInheritance

if TYPE_CHECKING:
    from monopoly.board import Tile
    from monopoly.game import Game
    from monopoly.player import Player


class AggressiveStrategy:
    """Buy everything; build everything; mortgage only under fire."""

    def decide_purchase(
        self, player: Player, tile: Tile, game_state: Game
    ) -> bool:
        if tile.price is None:
            return False
        return player.cash >= tile.price

    def decide_jail_action(self, player: Player, game_state: Game) -> JailAction:
        # Per spec: pay the fine to stay in circulation. The engine
        # automatically degrades to "roll" if cash < $50.
        return "pay"

    def decide_build(self, player: Player, game_state: Game) -> list[Tile]:
        return greedy_build_plan(
            player, game_state, eligible_monopolies(player, game_state)
        )

    def decide_mortgage(self, player: Player, game_state: Game) -> list[Tile]:
        if player.cash >= 0:
            return []
        # In trouble: mortgage anything that isn't already mortgaged. The
        # engine still blocks streets whose group has buildings, so
        # railroads / utilities and unbuilt streets go up first naturally.
        return [t for t in player.properties if not game_state.mortgaged[t.position]]

    def decide_unmortgage(self, player: Player, game_state: Game) -> list[Tile]:
        return []

    def decide_inherited_mortgage(
        self, player: Player, tile: Tile, game_state: Game
    ) -> MortgageInheritance:
        if tile.mortgage_value is None:
            return "keep_mortgaged"
        cost = math.ceil(tile.mortgage_value * 1.10)
        return "unmortgage" if player.cash >= cost else "keep_mortgaged"
