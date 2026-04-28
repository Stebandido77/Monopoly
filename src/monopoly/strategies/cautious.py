"""CautiousStrategy: cash-buffered conservative play.

Buys with a $200 buffer, builds slowly (one house per turn, only when
post-build cash exceeds $500), mortgages non-monopoly holdings first when
cash drops below $100, and unmortgages when cash exceeds $500. In jail,
prefers a held card, then paying the fine if comfortable, then rolling.

The thresholds are deliberately simple integers. They are tuned so the
strategy stays solvent through dry stretches but trades a fair amount of
expected return for that resilience — useful as a low-variance baseline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from monopoly.strategies.base import JailAction, MortgageInheritance

if TYPE_CHECKING:
    from monopoly.board import Tile
    from monopoly.game import Game
    from monopoly.player import Player


PURCHASE_BUFFER = 200
MIN_CASH_AFTER_BUILD = 500
MORTGAGE_THRESHOLD = 100
UNMORTGAGE_THRESHOLD = 500
JAIL_PAY_THRESHOLD = 500


class CautiousStrategy:
    """Conservative buyer / builder; mortgages only under cash pressure."""

    def decide_purchase(
        self, player: Player, tile: Tile, game_state: Game
    ) -> bool:
        if tile.price is None:
            return False
        return player.cash > tile.price + PURCHASE_BUFFER

    def decide_jail_action(self, player: Player, game_state: Game) -> JailAction:
        if player.jail_free_cards:
            return "card"
        if player.cash > JAIL_PAY_THRESHOLD:
            return "pay"
        return "roll"

    def decide_build(self, player: Player, game_state: Game) -> list[Tile]:
        for _color, group in game_state.board.color_groups.items():
            if not all(game_state.owners[t.position] is player for t in group):
                continue
            if any(game_state.mortgaged[t.position] for t in group):
                continue
            # Lowest-count tile first to respect uniformity.
            for tile in sorted(group, key=game_state._building_count):
                cost = tile.house_cost
                if cost is None:
                    continue
                if game_state._building_count(tile) >= 5:
                    continue
                if player.cash - cost > MIN_CASH_AFTER_BUILD:
                    return [tile]
                # Cash is the bottleneck for this group; further tiles in the
                # same group would cost the same. Try the next group.
                break
        return []

    def decide_mortgage(self, player: Player, game_state: Game) -> list[Tile]:
        if player.cash >= MORTGAGE_THRESHOLD:
            return []
        non_monopoly: list[Tile] = []
        monopoly: list[Tile] = []
        for tile in player.properties:
            if game_state.mortgaged[tile.position]:
                continue
            if tile.color_group is not None:
                group = game_state.board.color_groups[tile.color_group]
                full = all(game_state.owners[t.position] is player for t in group)
            else:
                # Railroads / utilities have no street-style monopoly; treat
                # them as non-monopoly so they go up first for liquidity.
                full = False
            (monopoly if full else non_monopoly).append(tile)
        return non_monopoly + monopoly

    def decide_unmortgage(self, player: Player, game_state: Game) -> list[Tile]:
        if player.cash <= UNMORTGAGE_THRESHOLD:
            return []
        return [t for t in player.properties if game_state.mortgaged[t.position]]

    def decide_inherited_mortgage(
        self, player: Player, tile: Tile, game_state: Game
    ) -> MortgageInheritance:
        return "keep_mortgaged"
