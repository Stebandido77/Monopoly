"""Mutable player state.

A :class:`Player` carries position, cash, owned properties, and the small
amount of jail / doubles bookkeeping needed by :class:`monopoly.game.Game`.
Decisions (whether to buy, how to leave jail, ...) live in strategies; this
class holds state only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from monopoly.board import Tile


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
        when buying or transferring properties.
    in_jail : bool
        Whether the player is currently in jail. While in jail the player
        does not move except to attempt an escape via doubles or by paying
        the fine.
    jail_turns : int
        Number of failed escape attempts since being jailed. After the
        third attempt the player is forced to pay the $50 fine and move.
    doubles_streak : int
        Consecutive doubles rolled in the current turn. Resets at the
        start of every non-jail turn and on going to jail. Three doubles
        in a single turn send the player to jail.
    """

    name: str
    position: int = 0
    cash: int = 1500
    properties: list[Tile] = field(default_factory=list)
    in_jail: bool = False
    jail_turns: int = 0
    doubles_streak: int = 0
