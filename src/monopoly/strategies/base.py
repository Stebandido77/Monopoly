"""Strategy protocol consulted by :class:`monopoly.game.Game`.

A strategy is any object exposing the decision points the engine calls into.
Phase 1 added ``decide_purchase`` and ``decide_jail_action``. Phase 2
introduces optional construction / mortgage / inheritance hooks. All
Phase-2 hooks have safe defaults (no-op or ``"keep_mortgaged"``) so existing
strategies remain valid: the engine probes for them with ``getattr`` and
falls back when missing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from monopoly.board import Tile
    from monopoly.game import Game
    from monopoly.player import Player

JailAction = Literal["pay", "roll", "card"]
"""Allowed return values for :meth:`Strategy.decide_jail_action`.

``"pay"`` means pay the $50 fine and roll. ``"roll"`` attempts doubles.
``"card"`` consumes a Get-Out-of-Jail-Free card if held; otherwise the
engine treats it as ``"roll"`` (ADR-001 closure in Phase 2).
"""

MortgageInheritance = Literal["keep_mortgaged", "unmortgage"]
"""Decision values for :meth:`Strategy.decide_inherited_mortgage`."""


@runtime_checkable
class Strategy(Protocol):
    """Decision-making interface for a Monopoly player.

    The engine never inspects player state directly to decide actions — it
    always asks a Strategy. A player with no strategy registered will
    refuse to buy and will always attempt a doubles roll out of jail.

    Phase-2 hooks (``decide_build``, ``decide_mortgage``,
    ``decide_unmortgage``, ``decide_inherited_mortgage``) are optional in
    practice: the engine probes via ``getattr`` so strategies that omit
    them inherit the safe defaults below.
    """

    # --- Phase 1 (required) ----------------------------------------------

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

    # --- Phase 2 (optional, default no-op via getattr probe) -------------

    def decide_build(self, player: Player, game_state: Game) -> list[Tile]:
        """Properties on which to build (in priority order). Default: ``[]``."""
        ...

    def decide_mortgage(
        self, player: Player, game_state: Game
    ) -> list[Tile]:
        """Properties to mortgage to raise cash. Default: ``[]``."""
        ...

    def decide_unmortgage(
        self, player: Player, game_state: Game
    ) -> list[Tile]:
        """Properties to lift the mortgage on. Default: ``[]``."""
        ...

    def decide_inherited_mortgage(
        self, player: Player, tile: Tile, game_state: Game
    ) -> MortgageInheritance:
        """How to handle a mortgaged property received via creditor bankruptcy.

        Default: ``"keep_mortgaged"``.
        """
        ...
