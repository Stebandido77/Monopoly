"""Strategy protocol consulted by :class:`monopoly.game.Game`.

A strategy is any object exposing :meth:`decide_purchase` and
:meth:`decide_jail_action`. Implementations are passed in via
``Game(strategies={player_name: strategy})``.

Phase 1 deliberately exposes only the two decision points required for the
current scope (purchase and jail). Building / mortgaging / trading hooks
will be added when those mechanics enter the engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from monopoly.board import Tile
    from monopoly.game import Game
    from monopoly.player import Player

JailAction = Literal["pay", "roll", "card"]
"""Allowed return values for :meth:`Strategy.decide_jail_action`.

``"pay"`` means pay the $50 fine and roll. ``"roll"`` means attempt to
escape via doubles. ``"card"`` is reserved for the get-out-of-jail-free
card and is treated as ``"roll"`` until cards are implemented.
"""


@runtime_checkable
class Strategy(Protocol):
    """Decision-making interface for a Monopoly player.

    The game engine never inspects player state directly to decide
    purchases or jail actions — it always asks a Strategy. A player with
    no strategy registered will refuse to buy and will always attempt a
    doubles roll out of jail.
    """

    def decide_purchase(
        self, player: Player, tile: Tile, game_state: Game
    ) -> bool:
        """Whether to buy ``tile`` at its listed price."""
        ...

    def decide_jail_action(
        self, player: Player, game_state: Game
    ) -> JailAction:
        """Whether to pay the fine, roll for doubles, or use a card."""
        ...
