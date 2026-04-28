"""Monopoly game engine.

Phase 1 scope: movement (with the GO salary paid for landing on or passing
GO), the doubles bonus rule (and three-doubles-to-jail), and jail handling
(escape via doubles, paying the $50 fine, or the forced-pay-and-move on the
third failed attempt). Property purchase, rent, and bankruptcy are added in
later commits in this phase.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from monopoly.board import Board, Tile
from monopoly.player import Player

if TYPE_CHECKING:
    from monopoly.strategies.base import Strategy


class Game:
    """Stateful Monopoly game.

    Parameters
    ----------
    players : list[Player]
        Active players. Turn order matches the list order.
    board : Board
        Static board configuration.
    strategies : dict[str, Strategy] or None
        Map from ``player.name`` to a Strategy. Players without a strategy
        will refuse to buy and will always attempt to roll out of jail.
    seed : int or None
        Seed for the dice RNG. Pass ``None`` for system entropy.

    Notes
    -----
    The dice RNG (:attr:`rng`) is the only source of randomness in the
    engine. All stochastic helpers go through it so that, given a fixed
    seed and deterministic strategies, a full game replays identically.
    """

    def __init__(
        self,
        players: list[Player],
        board: Board,
        strategies: dict[str, Strategy] | None = None,
        seed: int | None = None,
    ) -> None:
        self.players: list[Player] = players
        self.board: Board = board
        self.strategies: dict[str, Strategy] = dict(strategies) if strategies else {}
        self.rng: np.random.Generator = np.random.default_rng(seed)
        self._jail_position: int = next(
            t.position for t in board.tiles if t.type == "jail"
        )

    def roll_dice(self) -> tuple[int, int]:
        """Roll two six-sided dice using the game's RNG."""
        d1 = int(self.rng.integers(1, 7))
        d2 = int(self.rng.integers(1, 7))
        return d1, d2

    def move_player(self, player: Player, steps: int) -> Tile:
        """Advance ``player`` by ``steps`` tiles and pay GO salary on a wrap.

        Per Hasbro rules, $200 is paid whether the player lands on or merely
        passes GO. Moving zero or negative steps does not pay salary
        (negative is unused in Phase 1 but kept safe for future cards).

        Returns
        -------
        Tile
            The destination tile.
        """
        if steps <= 0:
            player.position = (player.position + steps) % len(self.board)
            return self.board.tiles[player.position]
        unwrapped = player.position + steps
        new_pos = unwrapped % len(self.board)
        if new_pos < unwrapped:
            # Wrapped past 0: passed (or landed on) GO exactly once.
            player.cash += self.board.bank.go_salary
        player.position = new_pos
        return self.board.tiles[new_pos]

    def _send_to_jail(self, player: Player) -> None:
        """Move ``player`` to jail and reset jail / doubles bookkeeping."""
        player.position = self._jail_position
        player.in_jail = True
        player.jail_turns = 0
        player.doubles_streak = 0

    def handle_jail(self, player: Player) -> tuple[int, int] | None:
        """Resolve the jail portion of a turn for ``player``.

        Per Hasbro rules, on each turn in jail a player may either pay the
        $50 fine and roll, or attempt to roll doubles to escape. After three
        failed attempts the player must pay the fine and move per the dice.
        Cards are not yet implemented and a ``"card"`` decision falls
        through to ``"roll"``.

        Returns
        -------
        tuple[int, int] or None
            The dice rolled if the player exits jail this turn (caller
            should resolve movement); ``None`` if the player remains in jail.
        """
        strategy = self.strategies.get(player.name)
        action = "roll"
        if strategy is not None:
            decision = strategy.decide_jail_action(player, self)
            if decision == "pay":
                action = "pay"

        fine = self.board.bank.jail_fine
        if action == "pay" and player.cash >= fine:
            player.cash -= fine
            player.in_jail = False
            player.jail_turns = 0
            player.doubles_streak = 0
            return self.roll_dice()

        d1, d2 = self.roll_dice()
        if d1 == d2:
            # Per Hasbro rules, a doubles escape ends the turn after moving
            # — no bonus roll. doubles_streak is reset to enforce that.
            player.in_jail = False
            player.jail_turns = 0
            player.doubles_streak = 0
            return d1, d2

        player.jail_turns += 1
        if player.jail_turns >= 3:
            player.cash -= fine  # may go negative; bankruptcy resolved later
            player.in_jail = False
            player.jail_turns = 0
            player.doubles_streak = 0
            return d1, d2

        return None

    def play_turn(self, player: Player) -> None:
        """Execute one full turn for ``player``.

        In this phase the turn covers: jail resolution; rolling for doubles
        with the bonus-roll rule; landing on the Go-to-Jail tile; and the
        three-doubles-to-jail rule. Property landings and tax/rent payments
        are handled in subsequent commits.
        """
        if player.cash < 0:
            return  # already out (bankruptcy implemented in a later commit)

        if player.in_jail:
            roll = self.handle_jail(player)
            if roll is None:
                return
            d1, d2 = roll
            self._move_and_resolve(player, d1 + d2)
            return

        player.doubles_streak = 0
        while True:
            d1, d2 = self.roll_dice()
            is_double = d1 == d2
            if is_double:
                player.doubles_streak += 1
                if player.doubles_streak >= 3:
                    self._send_to_jail(player)
                    return

            self._move_and_resolve(player, d1 + d2)

            if player.in_jail:
                # Sent there mid-turn (e.g., landed on Go to Jail).
                return
            if not is_double:
                return

    def _move_and_resolve(self, player: Player, steps: int) -> None:
        """Move and apply only the landings handled in this phase.

        Currently: ``go_to_jail`` sends the player to jail. All other
        landing effects (purchase, rent, tax) are added in later commits.
        """
        tile = self.move_player(player, steps)
        if tile.type == "go_to_jail":
            self._send_to_jail(player)

    def play(self, max_turns: int = 1000) -> Player | None:
        """Run the game for at most ``max_turns`` rounds and return a winner.

        A "round" is one full pass over :attr:`players`. The game ends when
        at most one player has non-negative cash, or when ``max_turns``
        rounds have elapsed (in which case the player with the most cash
        wins by default). Returns ``None`` if no player survives.
        """
        for _ in range(max_turns):
            survivors = [p for p in self.players if p.cash >= 0]
            if len(survivors) <= 1:
                break
            for player in self.players:
                if player.cash < 0:
                    continue
                self.play_turn(player)
        survivors = [p for p in self.players if p.cash >= 0]
        if not survivors:
            return None
        if len(survivors) == 1:
            return survivors[0]
        return max(survivors, key=lambda p: p.cash)
