"""Monopoly game engine.

Phase 1 covers: movement (with the GO salary paid for landing on or
passing GO), the doubles bonus rule (and three-doubles-to-jail), jail
handling (escape via doubles, paying the $50 fine, or the forced fine on
the third failed attempt), property purchase via the player's strategy,
rent (with the monopoly-doubling rule for streets, the 25/50/100/200 rent
schedule for railroads, and the 4x/10x dice-roll multiplier for utilities),
and simple bank-only bankruptcy.

Out of scope this phase: house and hotel construction, mortgages, Chance
and Community Chest cards, auctions, trading, and bankruptcy with a
creditor.
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
    verbose : bool
        When ``True``, :meth:`play_turn` prints one line per key event
        (roll, move, purchase, rent, jail transitions, bankruptcy) for
        manual debugging. Adds no new events to the engine itself; it only
        narrates the existing flow. Defaults to ``False``.

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
        verbose: bool = False,
    ) -> None:
        self.players: list[Player] = players
        self.board: Board = board
        self.strategies: dict[str, Strategy] = dict(strategies) if strategies else {}
        self.rng: np.random.Generator = np.random.default_rng(seed)
        self.verbose: bool = verbose
        self._turn: int = 0
        self.owners: dict[int, Player | None] = {
            t.position: None for t in board.tiles if t.is_property
        }
        self._jail_position: int = next(
            t.position for t in board.tiles if t.type == "jail"
        )

    # ------------------------------------------------------------------
    # Verbose-mode helpers (no behavior change when verbose is False)
    # ------------------------------------------------------------------

    def _emit_action(self, player: Player, action: str, cash_before: int) -> None:
        """Print one action line ``[T#] name: action (cash: $a→$b)`` if verbose."""
        if not self.verbose:
            return
        print(
            f"[T{self._turn}] {player.name}: {action} "
            f"(cash: ${cash_before}→${player.cash})"
        )

    def _roll_and_log(self, player: Player) -> tuple[int, int]:
        """Roll the dice and (in verbose mode) log the outcome."""
        d1, d2 = self.roll_dice()
        if self.verbose:
            suffix = " *DOBLE*" if d1 == d2 else ""
            print(f"[T{self._turn}] {player.name}: roll ({d1},{d2})={d1 + d2}{suffix}")
        return d1, d2

    # ------------------------------------------------------------------
    # Engine
    # ------------------------------------------------------------------

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
        old_pos = player.position
        passed_go = False
        if steps <= 0:
            new_pos = (old_pos + steps) % len(self.board)
        else:
            unwrapped = old_pos + steps
            new_pos = unwrapped % len(self.board)
            if new_pos < unwrapped:
                # Wrapped past 0: passed (or landed on) GO exactly once.
                player.cash += self.board.bank.go_salary
                passed_go = True
        player.position = new_pos
        tile = self.board.tiles[new_pos]
        if self.verbose:
            prefix = "💰 " if passed_go else ""
            suffix = " +$200 GO" if passed_go else ""
            print(
                f"[T{self._turn}] {player.name}: {prefix}pos {old_pos}→{new_pos} "
                f"({tile.name}){suffix}"
            )
        return tile

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
            cash_before = player.cash
            player.cash -= fine
            player.in_jail = False
            player.jail_turns = 0
            player.doubles_streak = 0
            self._emit_action(player, "🔒 pagó fianza $50", cash_before)
            return self._roll_and_log(player)

        d1, d2 = self._roll_and_log(player)
        if d1 == d2:
            # Per Hasbro rules, a doubles escape ends the turn after moving
            # — no bonus roll. doubles_streak is reset to enforce that.
            cash_before = player.cash
            player.in_jail = False
            player.jail_turns = 0
            player.doubles_streak = 0
            self._emit_action(player, "🔒 salió cárcel con doble", cash_before)
            return d1, d2

        player.jail_turns += 1
        if player.jail_turns >= 3:
            cash_before = player.cash
            player.cash -= fine  # may go negative; bankruptcy resolved later
            player.in_jail = False
            player.jail_turns = 0
            player.doubles_streak = 0
            self._emit_action(player, "🔒 fianza forzada $50", cash_before)
            return d1, d2

        return None

    def buy_property(self, player: Player, tile: Tile) -> bool:
        """Attempt purchase of ``tile`` by ``player``.

        Phase 1 has no auctions: when the lander declines (or has no
        strategy), the property simply remains in the bank's hand. Returns
        ``True`` iff the purchase happened.
        """
        if not tile.is_property:
            return False
        if self.owners[tile.position] is not None:
            return False
        if tile.price is None or player.cash < tile.price:
            self._emit_action(player, "sin dueño", player.cash)
            return False
        strategy = self.strategies.get(player.name)
        if strategy is None:
            self._emit_action(player, "sin dueño", player.cash)
            return False
        if not strategy.decide_purchase(player, tile, self):
            self._emit_action(player, "rechazó comprar", player.cash)
            return False
        cash_before = player.cash
        player.cash -= tile.price
        player.properties.append(tile)
        self.owners[tile.position] = player
        self._emit_action(player, f"compró {tile.name} por ${tile.price}", cash_before)
        return True

    def calculate_rent(self, tile: Tile, dice_roll: int) -> int:
        """Compute the rent owed for landing on ``tile``.

        Per Hasbro rules:

        * Streets pay the base rent, doubled when the owner holds the full
          color group with no buildings (Phase 1 has no buildings, so this
          is always the path taken on a complete group).
        * Railroads pay 25, 50, 100, or 200 for 1, 2, 3, or 4 owned by the
          same player.
        * Utilities pay 4x the dice roll if one is owned, 10x if both are.

        Returns 0 for unowned or self-owned tiles, and for tiles that are
        not properties.
        """
        owner = self.owners.get(tile.position)
        if owner is None:
            return 0
        if tile.type == "street":
            assert tile.rent is not None and tile.color_group is not None
            base = tile.rent[0]
            group = self.board.color_groups[tile.color_group]
            if all(self.owners[t.position] is owner for t in group):
                return base * 2
            return base
        if tile.type == "railroad":
            assert tile.rent is not None
            count = sum(
                1
                for r in self.board.tiles_by_type["railroad"]
                if self.owners[r.position] is owner
            )
            return tile.rent[count - 1]
        if tile.type == "utility":
            assert tile.rent_multipliers is not None
            count = sum(
                1
                for u in self.board.tiles_by_type["utility"]
                if self.owners[u.position] is owner
            )
            return tile.rent_multipliers[count - 1] * dice_roll
        return 0

    def pay_rent(self, payer: Player, tile: Tile, dice_roll: int) -> int:
        """Transfer rent from ``payer`` to the owner of ``tile``.

        Returns the amount paid (0 if unowned or self-owned). The payer's
        cash may go negative; bankruptcy is handled by
        :meth:`check_bankruptcy`.
        """
        owner = self.owners.get(tile.position)
        if owner is None or owner is payer:
            return 0
        rent = self.calculate_rent(tile, dice_roll)
        cash_before = payer.cash
        payer.cash -= rent
        owner.cash += rent
        self._emit_action(payer, f"💰 pagó renta ${rent} a {owner.name}", cash_before)
        return rent

    def check_bankruptcy(self, player: Player) -> bool:
        """If ``player.cash < 0``, return their properties to the bank.

        Phase 1 only models bankruptcy to the bank: any properties owned
        become unowned again and the player's holdings list is cleared.
        Bankruptcy with a creditor (where the creditor receives the
        properties) is out of scope for this phase.
        """
        if player.cash >= 0:
            return False
        cash_before = player.cash
        for tile in player.properties:
            self.owners[tile.position] = None
        player.properties.clear()
        self._emit_action(player, "💀 BANCARROTA", cash_before)
        return True

    def play_turn(self, player: Player) -> None:
        """Execute one full turn for ``player``.

        Resolves jail, doubles bonuses (and three-doubles-to-jail),
        movement, landing effects (Go-to-Jail, tax, property purchase or
        rent), and bankruptcy. Bankrupt players are skipped.
        """
        if player.cash < 0:
            return

        self._turn += 1

        if player.in_jail:
            roll = self.handle_jail(player)
            if roll is None:
                return
            d1, d2 = roll
            self._move_and_resolve(player, d1 + d2)
            self.check_bankruptcy(player)
            return

        player.doubles_streak = 0
        while True:
            d1, d2 = self._roll_and_log(player)
            is_double = d1 == d2
            if is_double:
                player.doubles_streak += 1
                if player.doubles_streak >= 3:
                    cash_before = player.cash
                    self._send_to_jail(player)
                    self._emit_action(player, "🔒 fue a cárcel (3 dobles)", cash_before)
                    return

            self._move_and_resolve(player, d1 + d2)

            if self.check_bankruptcy(player):
                return
            if player.in_jail:
                # Sent there mid-turn (e.g., landed on Go to Jail).
                return
            if not is_double:
                return

    def _move_and_resolve(self, player: Player, steps: int) -> None:
        """Move ``player`` and resolve the destination tile."""
        tile = self.move_player(player, steps)
        if tile.type == "go_to_jail":
            cash_before = player.cash
            self._send_to_jail(player)
            self._emit_action(player, "🔒 fue a cárcel", cash_before)
            return
        if tile.type == "tax":
            assert tile.tax_amount is not None
            cash_before = player.cash
            player.cash -= tile.tax_amount
            self._emit_action(player, f"💰 pagó impuesto ${tile.tax_amount}", cash_before)
            return
        if tile.is_property:
            owner = self.owners[tile.position]
            if owner is None:
                self.buy_property(player, tile)
            elif owner is not player:
                self.pay_rent(player, tile, steps)

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
