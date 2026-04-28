"""Mutable player state.

A :class:`Player` carries position, cash, owned properties, jail / doubles
bookkeeping, and the small Phase-2 additions: a list of held
"Get Out of Jail Free" cards and a back-reference to the :class:`Game` so
that the construction / mortgage public API can live on the player object
itself (``player.build_house(tile)`` rather than threading the game through
every call site).

Decisions (whether to buy, how to leave jail, where to build, ...) live in
strategies; this class still holds state only — the build / mortgage methods
are thin wrappers that delegate to the :class:`Game` rules engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from monopoly.board import Tile

if TYPE_CHECKING:
    from monopoly.cards import Card
    from monopoly.game import Game


@dataclass
class Player:
    """A Monopoly player.

    Parameters
    ----------
    name : str
        Display name. Also used as the key when looking up the player's
        strategy in :attr:`monopoly.game.Game.strategies`, so names must be
        unique within a game.
    position : int
        Current tile index (0..39). Defaults to 0 (GO).
    cash : int
        Cash on hand. Defaults to 1500 per Hasbro rules. May go negative
        transiently before :meth:`monopoly.game.Game.check_bankruptcy` runs.
    properties : list[Tile]
        Tiles currently owned by this player. Mutated by :class:`Game`
        when buying, transferring, or losing properties.
    in_jail : bool
        Whether the player is currently in jail.
    jail_turns : int
        Number of failed escape attempts since being jailed.
    doubles_streak : int
        Consecutive doubles rolled in the current turn.
    jail_free_cards : list[Card]
        "Get Out of Jail Free" cards held by the player. Drawn from
        Chance / Community Chest, kept until used in :meth:`Game.handle_jail`.
    """

    name: str
    position: int = 0
    cash: int = 1500
    properties: list[Tile] = field(default_factory=list)
    in_jail: bool = False
    jail_turns: int = 0
    doubles_streak: int = 0
    jail_free_cards: list[Card] = field(default_factory=list)
    _game: Game | None = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------------
    # Public API delegating to the rules engine. Each returns ``False``
    # silently if the operation cannot be performed for any reason
    # (no engine, not the owner, monopoly missing, inventory empty, etc.).
    # ------------------------------------------------------------------

    def build_house(self, tile: Tile) -> bool:
        """Build one house on ``tile``."""
        if self._game is None:
            return False
        return self._game._build_house(self, tile)

    def sell_house(self, tile: Tile) -> bool:
        """Sell one house from ``tile`` for half the house cost."""
        if self._game is None:
            return False
        return self._game._sell_house(self, tile)

    def build_hotel(self, tile: Tile) -> bool:
        """Upgrade ``tile`` from four houses to a hotel."""
        if self._game is None:
            return False
        return self._game._build_hotel(self, tile)

    def sell_hotel(self, tile: Tile) -> bool:
        """Downgrade ``tile`` from hotel back to four houses for half the hotel cost."""
        if self._game is None:
            return False
        return self._game._sell_hotel(self, tile)

    def mortgage(self, tile: Tile) -> bool:
        """Mortgage ``tile`` for its mortgage value."""
        if self._game is None:
            return False
        return self._game._mortgage(self, tile)

    def unmortgage(self, tile: Tile) -> bool:
        """Lift the mortgage on ``tile`` paying ``mortgage_value × 1.10`` (rounded up)."""
        if self._game is None:
            return False
        return self._game._unmortgage(self, tile)
