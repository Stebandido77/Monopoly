"""TargetedStrategy: focus on the high-traffic premium color groups.

Per the classic Markov-chain / stationary-distribution analyses of the
Monopoly board, the orange / red / yellow color groups receive
disproportionate landings. The Jail anchor (~3.95% landing probability
once the "Go to Jail" tile, the Chance / Community Chest cards, and the
3-doubles rule are accounted for) feeds into ranges of typical 2-die rolls
that hit those groups, and the Chance "advance to Illinois Avenue" /
"advance to Reading Railroad" cards reinforce the orange / red region.

Behaviour summary:

* Decline every purchase outside the premium set.
* Build aggressively when it owns one of those monopolies (delegates to
  the same greedy planner as :class:`AggressiveStrategy`).
* Mortgage / unmortgage / jail / inheritance: same conservative defaults
  as :class:`CautiousStrategy`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from monopoly.strategies._build_plan import eligible_monopolies, greedy_build_plan
from monopoly.strategies.base import JailAction, MortgageInheritance
from monopoly.strategies.cautious import CautiousStrategy

if TYPE_CHECKING:
    from monopoly.board import Tile
    from monopoly.game import Game
    from monopoly.player import Player

PREMIUM_GROUPS: set[str] = {"orange", "red", "yellow"}
PURCHASE_BUFFER = 100


class TargetedStrategy:
    """Buy only orange/red/yellow; build aggressively on those monopolies."""

    def __init__(self) -> None:
        # Composition over inheritance: Targeted's mortgage / unmortgage /
        # jail policies match Cautious exactly, so we delegate.
        self._cautious = CautiousStrategy()

    def decide_purchase(
        self, player: Player, tile: Tile, game_state: Game
    ) -> bool:
        if tile.color_group not in PREMIUM_GROUPS:
            return False
        if tile.price is None:
            return False
        return player.cash > tile.price + PURCHASE_BUFFER

    def decide_jail_action(self, player: Player, game_state: Game) -> JailAction:
        return self._cautious.decide_jail_action(player, game_state)

    def decide_build(self, player: Player, game_state: Game) -> list[Tile]:
        monopolies = eligible_monopolies(player, game_state, PREMIUM_GROUPS)
        return greedy_build_plan(player, game_state, monopolies)

    def decide_mortgage(self, player: Player, game_state: Game) -> list[Tile]:
        return self._cautious.decide_mortgage(player, game_state)

    def decide_unmortgage(self, player: Player, game_state: Game) -> list[Tile]:
        return self._cautious.decide_unmortgage(player, game_state)

    def decide_inherited_mortgage(
        self, player: Player, tile: Tile, game_state: Game
    ) -> MortgageInheritance:
        return self._cautious.decide_inherited_mortgage(player, tile, game_state)
