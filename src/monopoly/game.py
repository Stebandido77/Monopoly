"""Monopoly game engine.

Phase 2 covers, on top of Phase 1: house and hotel construction with
uniform-building and bank-inventory rules, mortgages (and unmortgages with
10% interest), Chance and Community Chest decks, and bankruptcy with a
creditor (debtor's properties, mortgages, houses and hotels transfer per
ADR-001 / ADR-003).

Out of scope still: trading between players (Strategy.propose_trade is the
extension point), and auctions when a player declines or goes bankrupt to
the bank (per ADR-003 the property simply returns to the bank).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Literal

import numpy as np

from monopoly.board import Board, Tile
from monopoly.cards import (
    Card,
    Deck,
    default_chance_path,
    default_community_chest_path,
    load_cards,
)
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
        Seed for the dice / deck RNG.
    verbose : bool
        Narrate one line per key event when ``True``.
    chance_deck, community_chest_deck : Deck or None
        Override the default decks (loaded from ``data/*.yaml``). Useful in
        tests to force a specific draw order.

    Notes
    -----
    The :attr:`rng` is the only source of randomness in the engine. Both
    dice rolls and the initial deck shuffles consume from it, so a fixed
    seed and deterministic strategies replay identically.
    """

    def __init__(
        self,
        players: list[Player],
        board: Board,
        strategies: dict[str, Strategy] | None = None,
        seed: int | None = None,
        verbose: bool = False,
        chance_deck: Deck | None = None,
        community_chest_deck: Deck | None = None,
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

        # Phase 2: per-tile mutable state.
        self.houses: dict[int, int] = {
            t.position: 0 for t in board.tiles if t.type == "street"
        }
        self.hotels: dict[int, bool] = {
            t.position: False for t in board.tiles if t.type == "street"
        }
        self.mortgaged: dict[int, bool] = {
            t.position: False for t in board.tiles if t.is_property
        }
        self.available_houses: int = board.bank.total_houses
        self.available_hotels: int = board.bank.total_hotels

        # Decks. Default to bundled YAMLs; tests can inject deterministic decks.
        if chance_deck is None:
            chance_deck = Deck(load_cards(default_chance_path()), self.rng)
        if community_chest_deck is None:
            community_chest_deck = Deck(
                load_cards(default_community_chest_path()), self.rng
            )
        self.chance_deck: Deck = chance_deck
        self.community_chest_deck: Deck = community_chest_deck

        # Back-reference so player.build_house(tile) can delegate here.
        for player in self.players:
            player._game = self

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
    # Bank-inventory accessors (Phase 2 public API)
    # ------------------------------------------------------------------

    def get_available_houses(self) -> int:
        """Houses remaining in the bank's pool (out of 32)."""
        return self.available_houses

    def get_available_hotels(self) -> int:
        """Hotels remaining in the bank's pool (out of 12)."""
        return self.available_hotels

    # ------------------------------------------------------------------
    # Engine: dice / movement / jail
    # ------------------------------------------------------------------

    def roll_dice(self) -> tuple[int, int]:
        """Roll two six-sided dice using the game's RNG."""
        d1 = int(self.rng.integers(1, 7))
        d2 = int(self.rng.integers(1, 7))
        return d1, d2

    def move_player(self, player: Player, steps: int) -> Tile:
        """Advance ``player`` by ``steps`` tiles and pay GO salary on a wrap.

        Per Hasbro rules, $200 is paid whether the player lands on or merely
        passes GO. Moving zero or negative steps does not pay salary.
        """
        old_pos = player.position
        cash_before = player.cash
        passed_go = False
        if steps <= 0:
            new_pos = (old_pos + steps) % len(self.board)
        else:
            unwrapped = old_pos + steps
            new_pos = unwrapped % len(self.board)
            if new_pos < unwrapped:
                player.cash += self.board.bank.go_salary
                passed_go = True
        player.position = new_pos
        tile = self.board.tiles[new_pos]
        if self.verbose:
            prefix = "💰 " if passed_go else ""
            if passed_go:
                salary = self.board.bank.go_salary
                suffix = f" +${salary} GO (cash: ${cash_before}→${player.cash})"
            else:
                suffix = ""
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

        Per Hasbro rules, on each turn in jail a player may pay the $50 fine
        and roll, attempt doubles, or — per ADR-001 closure in Phase 2 —
        play a "Get Out of Jail Free" card if they hold one. After three
        failed doubles attempts the player must pay the fine and move.

        Returns
        -------
        tuple[int, int] or None
            The dice rolled if the player exits jail this turn (caller
            resolves the resulting movement); ``None`` if the player
            remains in jail.
        """
        strategy = self.strategies.get(player.name)
        action: Literal["pay", "roll", "card"] = "roll"
        if strategy is not None:
            decision = strategy.decide_jail_action(player, self)
            if decision in ("pay", "card"):
                action = decision

        # Card path: consume a held jail-free card if available; otherwise fall
        # through to the standard roll path (ADR-001 closure).
        if action == "card" and player.jail_free_cards:
            card = player.jail_free_cards.pop(0)
            cash_before = player.cash
            player.in_jail = False
            player.jail_turns = 0
            player.doubles_streak = 0
            self._return_jail_card(card)
            self._emit_action(player, "🔒 usó carta sal-de-cárcel", cash_before)
            return self._roll_and_log(player)
        if action == "card":
            action = "roll"

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
            cash_before = player.cash
            player.in_jail = False
            player.jail_turns = 0
            player.doubles_streak = 0
            self._emit_action(player, "🔒 salió cárcel con doble", cash_before)
            return d1, d2

        player.jail_turns += 1
        if player.jail_turns >= 3:
            cash_before = player.cash
            player.cash -= fine
            player.in_jail = False
            player.jail_turns = 0
            player.doubles_streak = 0
            self._emit_action(player, "🔒 fianza forzada $50", cash_before)
            return d1, d2

        return None

    # ------------------------------------------------------------------
    # Property purchase & rent
    # ------------------------------------------------------------------

    def buy_property(self, player: Player, tile: Tile) -> bool:
        """Attempt purchase of ``tile`` by ``player``.

        Phase 1/2 has no auctions (see ADR-003): when the lander declines
        or has no strategy, the property simply remains in the bank.
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

        * Mortgaged properties charge no rent.
        * Streets pay the rent for their current building level (base, 1-4
          houses, or hotel). Base rent doubles on a complete unbuilt
          monopoly.
        * Railroads pay 25/50/100/200 for 1/2/3/4 *unmortgaged* railroads
          owned by the same player.
        * Utilities pay 4x the dice roll if one *unmortgaged* utility is
          owned, 10x if both are.

        Returns 0 for unowned, self-owned, mortgaged, or non-property tiles.
        """
        owner = self.owners.get(tile.position)
        if owner is None:
            return 0
        if self.mortgaged.get(tile.position, False):
            return 0
        if tile.type == "street":
            assert tile.rent is not None and tile.color_group is not None
            if self.hotels[tile.position]:
                return tile.rent[5]
            houses = self.houses[tile.position]
            if houses > 0:
                return tile.rent[houses]
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
                if self.owners[r.position] is owner and not self.mortgaged[r.position]
            )
            if count == 0:
                return 0
            return tile.rent[count - 1]
        if tile.type == "utility":
            assert tile.rent_multipliers is not None
            count = sum(
                1
                for u in self.board.tiles_by_type["utility"]
                if self.owners[u.position] is owner and not self.mortgaged[u.position]
            )
            if count == 0:
                return 0
            return tile.rent_multipliers[count - 1] * dice_roll
        return 0

    def pay_rent(self, payer: Player, tile: Tile, dice_roll: int) -> int:
        """Transfer rent from ``payer`` to the owner of ``tile``.

        Returns the amount paid. The payer's cash may go negative;
        bankruptcy is resolved by :meth:`check_bankruptcy` (called by the
        landing resolver, with the owner as creditor).
        """
        owner = self.owners.get(tile.position)
        if owner is None or owner is payer:
            return 0
        rent = self.calculate_rent(tile, dice_roll)
        if rent == 0:
            return 0
        cash_before = payer.cash
        payer.cash -= rent
        owner.cash += rent
        self._emit_action(payer, f"💰 pagó renta ${rent} a {owner.name}", cash_before)
        return rent

    # ------------------------------------------------------------------
    # Construction (Phase 2)
    # ------------------------------------------------------------------

    def _is_full_monopoly(self, player: Player, color_group: str) -> bool:
        """Whether ``player`` owns every street in ``color_group``."""
        return all(
            self.owners[t.position] is player
            for t in self.board.color_groups[color_group]
        )

    def _group_has_buildings(self, color_group: str) -> bool:
        """Any house or hotel anywhere in ``color_group``."""
        return any(
            self.houses[t.position] > 0 or self.hotels[t.position]
            for t in self.board.color_groups[color_group]
        )

    def _building_count(self, tile: Tile) -> int:
        """Building level on ``tile``: 0..4 houses, or 5 for a hotel."""
        if self.hotels[tile.position]:
            return 5
        return self.houses[tile.position]

    def _check_uniformity(
        self, color_group: str, target_pos: int, new_count: int
    ) -> bool:
        """Whether setting ``target_pos`` to ``new_count`` keeps max-min ≤ 1."""
        counts = [
            new_count if t.position == target_pos else self._building_count(t)
            for t in self.board.color_groups[color_group]
        ]
        return max(counts) - min(counts) <= 1

    def _build_house(self, player: Player, tile: Tile) -> bool:
        """Backend for :meth:`Player.build_house`. Returns False on any failure."""
        if tile.type != "street" or tile.color_group is None:
            return False
        if self.owners.get(tile.position) is not player:
            return False
        if not self._is_full_monopoly(player, tile.color_group):
            return False
        if any(
            self.mortgaged[t.position] for t in self.board.color_groups[tile.color_group]
        ):
            return False
        if self.hotels[tile.position]:
            return False
        if self.houses[tile.position] >= 4:
            return False
        if self.available_houses < 1:
            self._emit_action(
                player, f"❌ sin inventario casas ({tile.name})", player.cash
            )
            return False
        new_count = self.houses[tile.position] + 1
        if not self._check_uniformity(tile.color_group, tile.position, new_count):
            return False
        if tile.house_cost is None or player.cash < tile.house_cost:
            return False
        cash_before = player.cash
        player.cash -= tile.house_cost
        self.houses[tile.position] = new_count
        self.available_houses -= 1
        self._emit_action(
            player, f"🏠 construyó casa #{new_count} en {tile.name}", cash_before
        )
        return True

    def _build_hotel(self, player: Player, tile: Tile) -> bool:
        """Backend for :meth:`Player.build_hotel`. Requires 4 houses; returns 4 to bank."""
        if tile.type != "street" or tile.color_group is None:
            return False
        if self.owners.get(tile.position) is not player:
            return False
        if not self._is_full_monopoly(player, tile.color_group):
            return False
        if any(
            self.mortgaged[t.position] for t in self.board.color_groups[tile.color_group]
        ):
            return False
        if self.hotels[tile.position]:
            return False
        if self.houses[tile.position] != 4:
            return False
        if self.available_hotels < 1:
            self._emit_action(
                player, f"❌ sin inventario hoteles ({tile.name})", player.cash
            )
            return False
        if not self._check_uniformity(tile.color_group, tile.position, 5):
            return False
        if tile.house_cost is None or player.cash < tile.house_cost:
            return False
        cash_before = player.cash
        player.cash -= tile.house_cost
        self.houses[tile.position] = 0
        self.hotels[tile.position] = True
        self.available_houses += 4
        self.available_hotels -= 1
        self._emit_action(player, f"🏨 construyó hotel en {tile.name}", cash_before)
        return True

    def _sell_house(self, player: Player, tile: Tile) -> bool:
        """Backend for :meth:`Player.sell_house`. Returns half the house cost."""
        if tile.type != "street" or tile.color_group is None:
            return False
        if self.owners.get(tile.position) is not player:
            return False
        if self.hotels[tile.position]:
            return False
        if self.houses[tile.position] < 1:
            return False
        if tile.house_cost is None:
            return False
        new_count = self.houses[tile.position] - 1
        if not self._check_uniformity(tile.color_group, tile.position, new_count):
            return False
        cash_before = player.cash
        self.houses[tile.position] = new_count
        self.available_houses += 1
        player.cash += tile.house_cost // 2
        self._emit_action(
            player, f"🏠 vendió casa de {tile.name} por ${tile.house_cost // 2}", cash_before
        )
        return True

    def _sell_hotel(self, player: Player, tile: Tile) -> bool:
        """Backend for :meth:`Player.sell_hotel`. Downgrade hotel to four houses.

        Per Hasbro rules, downgrading a hotel requires 4 houses to be available
        in the bank inventory. If not, the operation fails silently.
        """
        if tile.type != "street" or tile.color_group is None:
            return False
        if self.owners.get(tile.position) is not player:
            return False
        if not self.hotels[tile.position]:
            return False
        if self.available_houses < 4:
            return False
        if tile.house_cost is None:
            return False
        if not self._check_uniformity(tile.color_group, tile.position, 4):
            return False
        cash_before = player.cash
        self.hotels[tile.position] = False
        self.houses[tile.position] = 4
        self.available_houses -= 4
        self.available_hotels += 1
        player.cash += tile.house_cost // 2
        self._emit_action(
            player, f"🏨 vendió hotel de {tile.name} por ${tile.house_cost // 2}", cash_before
        )
        return True

    # ------------------------------------------------------------------
    # Mortgages (Phase 2)
    # ------------------------------------------------------------------

    def _mortgage(self, player: Player, tile: Tile) -> bool:
        """Backend for :meth:`Player.mortgage`."""
        if not tile.is_property:
            return False
        if self.owners.get(tile.position) is not player:
            return False
        if self.mortgaged[tile.position]:
            return False
        if tile.mortgage_value is None:
            return False
        if (
            tile.type == "street"
            and tile.color_group is not None
            and self._group_has_buildings(tile.color_group)
        ):
            return False
        cash_before = player.cash
        self.mortgaged[tile.position] = True
        player.cash += tile.mortgage_value
        self._emit_action(
            player, f"💸 hipotecó {tile.name} por ${tile.mortgage_value}", cash_before
        )
        return True

    def _unmortgage(self, player: Player, tile: Tile) -> bool:
        """Backend for :meth:`Player.unmortgage`. Pay ``mortgage_value × 1.10`` (ceiling)."""
        if not tile.is_property:
            return False
        if self.owners.get(tile.position) is not player:
            return False
        if not self.mortgaged[tile.position]:
            return False
        if tile.mortgage_value is None:
            return False
        cost = math.ceil(tile.mortgage_value * 1.10)
        if player.cash < cost:
            return False
        cash_before = player.cash
        player.cash -= cost
        self.mortgaged[tile.position] = False
        self._emit_action(
            player, f"💸 deshipotecó {tile.name} por ${cost}", cash_before
        )
        return True

    # ------------------------------------------------------------------
    # Cards (Phase 2)
    # ------------------------------------------------------------------

    def draw_card(self, deck_type: str, player: Player) -> Card:
        """Draw the top card from ``deck_type`` (``"chance"`` or ``"community_chest"``).

        The card's effect is applied immediately. Get-out-of-jail-free cards
        stay with the player; everything else rotates to the bottom of the
        deck.
        """
        deck = self._deck_by_type(deck_type)
        card = deck.draw()
        if self.verbose:
            print(f"[T{self._turn}] {player.name}: 🃏 {deck_type} → {card.name}")
        self._apply_card_effect(card, player)
        if card.effect_type != "get_out_of_jail":
            deck.return_card(card)
        return card

    def _deck_by_type(self, deck_type: str) -> Deck:
        if deck_type == "chance":
            return self.chance_deck
        if deck_type == "community_chest":
            return self.community_chest_deck
        raise ValueError(f"Unknown deck type: {deck_type}")

    def _return_jail_card(self, card: Card) -> None:
        """Place a used Get-Out-of-Jail-Free card back on its origin deck."""
        origin = card.payload.get("deck", "chance")
        self._deck_by_type(origin).return_card(card)

    def _apply_card_effect(self, card: Card, player: Player) -> None:
        """Dispatch on ``card.effect_type``. See :mod:`monopoly.cards`."""
        et = card.effect_type
        if et == "move_to_position":
            self._effect_move_to_position(card, player)
        elif et == "move_to_nearest":
            self._effect_move_to_nearest(card, player)
        elif et == "move_relative":
            self._effect_move_relative(card, player)
        elif et == "collect":
            self._effect_collect(card, player)
        elif et == "pay":
            self._effect_pay(card, player)
        elif et == "collect_from_each_player":
            self._effect_collect_from_each(card, player)
        elif et == "pay_each_player":
            self._effect_pay_each(card, player)
        elif et == "pay_per_house_and_hotel":
            self._effect_pay_per_house_and_hotel(card, player)
        elif et == "go_to_jail":
            cash_before = player.cash
            self._send_to_jail(player)
            self._emit_action(player, "🔒 fue a cárcel (carta)", cash_before)
        elif et == "get_out_of_jail":
            player.jail_free_cards.append(card)
            self._emit_action(player, "🃏 recibió carta sal-de-cárcel", player.cash)
        else:
            raise ValueError(f"Unknown card effect: {et}")

    def _effect_move_to_position(self, card: Card, player: Player) -> None:
        target = int(card.payload["position"])
        pass_go = bool(card.payload.get("pass_go", True))
        if pass_go and target < player.position:
            cash_before = player.cash
            player.cash += self.board.bank.go_salary
            if self.verbose:
                print(
                    f"[T{self._turn}] {player.name}: 💰 GO (carta) "
                    f"+${self.board.bank.go_salary} (cash: ${cash_before}→${player.cash})"
                )
        player.position = target
        tile = self.board.tiles[target]
        if self.verbose:
            print(f"[T{self._turn}] {player.name}: ➡ {tile.name} (carta)")
        self._resolve_landing(player, tile, dice_roll=0)

    def _effect_move_to_nearest(self, card: Card, player: Player) -> None:
        target_type = card.payload["target_type"]
        targets = self.board.tiles_by_type[target_type]
        old_pos = player.position
        ahead = [t for t in targets if t.position > old_pos]
        if ahead:
            target_tile = min(ahead, key=lambda t: t.position)
            wrapped = False
        else:
            target_tile = min(targets, key=lambda t: t.position)
            wrapped = True
        if wrapped:
            player.cash += self.board.bank.go_salary
        player.position = target_tile.position
        if self.verbose:
            print(
                f"[T{self._turn}] {player.name}: ➡ {target_tile.name} (carta nearest)"
            )

        owner = self.owners.get(target_tile.position)
        if owner is None:
            self.buy_property(player, target_tile)
            return
        if owner is player:
            return
        if self.mortgaged[target_tile.position]:
            return
        if card.payload.get("pay_owner_double", False):
            if target_tile.type == "utility":
                d1, d2 = self.roll_dice()
                base = self.calculate_rent(target_tile, d1 + d2)
            else:
                base = self.calculate_rent(target_tile, 0)
            rent = base * 2
            cash_before = player.cash
            player.cash -= rent
            owner.cash += rent
            self._emit_action(
                player, f"💰 pagó x2 ${rent} a {owner.name} (carta)", cash_before
            )
            self.check_bankruptcy(player, creditor=owner)
        else:
            self.pay_rent(player, target_tile, 0)
            self.check_bankruptcy(player, creditor=owner)

    def _effect_move_relative(self, card: Card, player: Player) -> None:
        offset = int(card.payload["offset"])
        new_pos = (player.position + offset) % len(self.board)
        player.position = new_pos
        tile = self.board.tiles[new_pos]
        if self.verbose:
            print(
                f"[T{self._turn}] {player.name}: ↩ {tile.name} (carta {offset:+d})"
            )
        self._resolve_landing(player, tile, dice_roll=0)

    def _effect_collect(self, card: Card, player: Player) -> None:
        amount = int(card.payload["amount"])
        cash_before = player.cash
        player.cash += amount
        self._emit_action(player, f"💰 cobró ${amount} (carta)", cash_before)

    def _effect_pay(self, card: Card, player: Player) -> None:
        amount = int(card.payload["amount"])
        cash_before = player.cash
        player.cash -= amount
        self._emit_action(player, f"💰 pagó ${amount} al banco (carta)", cash_before)
        self.check_bankruptcy(player, creditor=None)

    def _effect_collect_from_each(self, card: Card, player: Player) -> None:
        amount = int(card.payload["amount"])
        for other in self.players:
            if other is player or other.cash < 0:
                continue
            other.cash -= amount
            player.cash += amount
            if other.cash < 0:
                self.check_bankruptcy(other, creditor=player)

    def _effect_pay_each(self, card: Card, player: Player) -> None:
        amount = int(card.payload["amount"])
        for other in self.players:
            if other is player or other.cash < 0:
                continue
            player.cash -= amount
            other.cash += amount
            if player.cash < 0:
                self.check_bankruptcy(player, creditor=other)
                return

    def _effect_pay_per_house_and_hotel(self, card: Card, player: Player) -> None:
        per_house = int(card.payload["per_house"])
        per_hotel = int(card.payload["per_hotel"])
        houses = sum(self.houses[t.position] for t in player.properties if t.type == "street")
        hotels = sum(
            1 for t in player.properties if t.type == "street" and self.hotels[t.position]
        )
        amount = per_house * houses + per_hotel * hotels
        if amount == 0:
            return
        cash_before = player.cash
        player.cash -= amount
        self._emit_action(
            player,
            f"🏠 reparaciones ${amount} ({houses}h + {hotels}H) (carta)",
            cash_before,
        )
        self.check_bankruptcy(player, creditor=None)

    # ------------------------------------------------------------------
    # Landing & turn loop
    # ------------------------------------------------------------------

    def _resolve_landing(self, player: Player, tile: Tile, dice_roll: int) -> None:
        """Resolve all effects of standing on ``tile`` (no movement here)."""
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
            self.check_bankruptcy(player, creditor=None)
            return
        if tile.type == "chance":
            self.draw_card("chance", player)
            return
        if tile.type == "community_chest":
            self.draw_card("community_chest", player)
            return
        if tile.is_property:
            owner = self.owners[tile.position]
            if owner is None:
                self.buy_property(player, tile)
            elif owner is not player:
                self.pay_rent(player, tile, dice_roll)
                self.check_bankruptcy(player, creditor=owner)

    def _move_and_resolve(self, player: Player, steps: int) -> None:
        """Move ``player`` ``steps`` tiles and resolve the destination."""
        tile = self.move_player(player, steps)
        self._resolve_landing(player, tile, steps)

    def play_turn(self, player: Player) -> None:
        """Execute one full turn for ``player``.

        After movement (and any bankruptcy) is resolved, the player gets a
        management phase: optional unmortgages, mortgages, and builds via
        their Strategy hooks. Skipped if the player is bankrupt or in jail
        afterwards.
        """
        if player.cash < 0:
            return

        self._turn += 1

        if player.in_jail:
            roll = self.handle_jail(player)
            if roll is None:
                self._management_phase(player)
                return
            d1, d2 = roll
            self._move_and_resolve(player, d1 + d2)
            self.check_bankruptcy(player)
            self._management_phase(player)
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
                return
            if not is_double:
                self._management_phase(player)
                return

    def _management_phase(self, player: Player) -> None:
        """Run the player's optional Strategy hooks for property management.

        Order: unmortgage → mortgage → build. Each hook may return an empty
        list (or be missing entirely on the strategy, in which case it is
        skipped). Each tile in a returned list is one attempt; failures are
        silent (per :meth:`Player.build_house` etc. semantics).
        """
        if player.cash < 0:
            return
        strategy = self.strategies.get(player.name)
        if strategy is None:
            return

        unmortgage_fn = getattr(strategy, "decide_unmortgage", None)
        if unmortgage_fn is not None:
            for tile in unmortgage_fn(player, self) or []:
                self._unmortgage(player, tile)

        mortgage_fn = getattr(strategy, "decide_mortgage", None)
        if mortgage_fn is not None:
            for tile in mortgage_fn(player, self) or []:
                self._mortgage(player, tile)

        build_fn = getattr(strategy, "decide_build", None)
        if build_fn is not None:
            for tile in build_fn(player, self) or []:
                if tile.type != "street":
                    continue
                if self.houses[tile.position] == 4 and not self.hotels[tile.position]:
                    self._build_hotel(player, tile)
                else:
                    self._build_house(player, tile)

    # ------------------------------------------------------------------
    # Bankruptcy (Phase 2: with creditor)
    # ------------------------------------------------------------------

    def check_bankruptcy(
        self, player: Player, creditor: Player | None = None
    ) -> bool:
        """If ``player.cash < 0``, liquidate to ``creditor`` (bank if None).

        Bank case (creditor is ``None``): all houses and hotels are returned
        to the bank inventory, properties become unowned, mortgage flags are
        cleared. Per ADR-003 there is no auction in v1.

        Creditor case (``creditor`` is a Player):

        1. All buildings the debtor owned are sold to the bank at half price;
           the cash goes to the creditor and the buildings return to the bank
           inventory.
        2. Each property is transferred to the creditor (preserving its
           mortgage flag).
        3. For each inherited mortgaged property the creditor's strategy
           decides between paying the 10% interest fee to keep it mortgaged
           or paying ``mortgage_value × 1.10`` to lift the mortgage. The
           default decision (no method on Strategy) is ``"keep_mortgaged"``.
        4. Held Get-Out-of-Jail-Free cards are returned to their decks.
        """
        if player.cash >= 0:
            return False
        cash_before = player.cash

        if creditor is None:
            for tile in list(player.properties):
                self._reclaim_to_bank(tile)
            player.properties.clear()
            self._return_held_jail_cards(player)
            self._emit_action(player, "💀 BANCARROTA (banco)", cash_before)
            return True

        # Creditor case: liquidate buildings to creditor, then transfer.
        for tile in list(player.properties):
            if tile.type == "street" and tile.house_cost is not None:
                house_count = self.houses[tile.position]
                if house_count > 0:
                    creditor.cash += (tile.house_cost // 2) * house_count
                    self.available_houses += house_count
                    self.houses[tile.position] = 0
                if self.hotels[tile.position]:
                    creditor.cash += tile.house_cost // 2
                    self.available_hotels += 1
                    self.hotels[tile.position] = False

        for tile in list(player.properties):
            self.owners[tile.position] = creditor
            creditor.properties.append(tile)
            if self.mortgaged[tile.position]:
                self._handle_inherited_mortgage(creditor, tile)

        player.properties.clear()
        self._return_held_jail_cards(player)
        self._emit_action(
            player, f"💀 BANCARROTA (acreedor: {creditor.name})", cash_before
        )
        return True

    def _reclaim_to_bank(self, tile: Tile) -> None:
        """Return ``tile`` and its buildings to the bank, clear mortgage."""
        self.owners[tile.position] = None
        if tile.type == "street":
            self.available_houses += self.houses[tile.position]
            self.houses[tile.position] = 0
            if self.hotels[tile.position]:
                self.available_hotels += 1
                self.hotels[tile.position] = False
        self.mortgaged[tile.position] = False

    def _return_held_jail_cards(self, player: Player) -> None:
        """Send any held Get-Out-of-Jail-Free cards back to their decks."""
        for card in player.jail_free_cards:
            self._return_jail_card(card)
        player.jail_free_cards.clear()

    def _handle_inherited_mortgage(self, creditor: Player, tile: Tile) -> None:
        """Apply creditor's choice for a mortgaged inherited tile."""
        assert tile.mortgage_value is not None
        decision: Literal["keep_mortgaged", "unmortgage"] = "keep_mortgaged"
        strategy = self.strategies.get(creditor.name)
        if strategy is not None:
            method = getattr(strategy, "decide_inherited_mortgage", None)
            if method is not None:
                decision = method(creditor, tile, self)
        if decision == "keep_mortgaged":
            fee = math.ceil(tile.mortgage_value * 0.10)
            creditor.cash -= fee
            self._emit_action(
                creditor, f"hereda hipoteca {tile.name} (10% ${fee})", creditor.cash + fee
            )
        else:
            fee = math.ceil(tile.mortgage_value * 1.10)
            creditor.cash -= fee
            self.mortgaged[tile.position] = False
            self._emit_action(
                creditor,
                f"hereda y deshipoteca {tile.name} (${fee})",
                creditor.cash + fee,
            )

    # ------------------------------------------------------------------
    # Game loop
    # ------------------------------------------------------------------

    def play(self, max_turns: int = 1000) -> Player | None:
        """Run the game for at most ``max_turns`` rounds and return a winner."""
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
