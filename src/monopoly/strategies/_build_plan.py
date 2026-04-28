"""Greedy build planner shared between Aggressive and Targeted strategies.

Both strategies want to spend until cash is exhausted, building round-robin
on the lowest-count tile of every eligible monopoly to keep the engine's
uniformity guard happy. They differ only in *which* monopolies count as
eligible (Aggressive: any owned monopoly; Targeted: orange/red/yellow
only). Factoring the inner loop here keeps both call sites short.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from monopoly.board import Tile
    from monopoly.game import Game
    from monopoly.player import Player


def greedy_build_plan(
    player: Player, game_state: Game, monopolies: list[list[Tile]]
) -> list[Tile]:
    """Plan a build sequence that maxes out ``monopolies`` within budget.

    Picks the lowest-count tile of each group on each pass (round-robin),
    upgrading from 4 houses to a hotel when uniformity allows. Stops when
    no group can take another build (budget, inventory, or fully maxed).
    Returns the list of tiles in build order, ready to feed back to
    :meth:`Game._management_phase`.
    """
    chosen: list[Tile] = []
    sim_houses = dict(game_state.houses)
    sim_hotels = dict(game_state.hotels)
    sim_houses_avail = game_state.available_houses
    sim_hotels_avail = game_state.available_hotels
    sim_cash = player.cash

    def count(t: Tile) -> int:
        return 5 if sim_hotels[t.position] else sim_houses[t.position]

    while True:
        progress = False
        for group in monopolies:
            if all(count(t) == 5 for t in group):
                continue
            tile = min(group, key=count)
            cur = count(tile)
            cost = tile.house_cost
            if cost is None or sim_cash < cost:
                continue
            if cur == 4:
                if sim_hotels_avail < 1:
                    continue
                if any(count(t) < 4 for t in group):
                    continue
                chosen.append(tile)
                sim_cash -= cost
                sim_hotels[tile.position] = True
                sim_houses[tile.position] = 0
                sim_houses_avail += 4
                sim_hotels_avail -= 1
                progress = True
            else:
                if sim_houses_avail < 1:
                    continue
                new_count = cur + 1
                others = [count(t) for t in group if t.position != tile.position]
                if max([new_count, *others]) - min([new_count, *others]) > 1:
                    continue
                chosen.append(tile)
                sim_cash -= cost
                sim_houses[tile.position] = new_count
                sim_houses_avail -= 1
                progress = True
        if not progress:
            break
    return chosen


def eligible_monopolies(
    player: Player,
    game_state: Game,
    color_filter: set[str] | None = None,
) -> list[list[Tile]]:
    """List the player's full color-group monopolies, optionally filtered.

    A monopoly is eligible only if no tile in the group is mortgaged: per
    the engine, a single mortgaged tile blocks construction across the
    whole group.
    """
    out: list[list[Tile]] = []
    for color, group in game_state.board.color_groups.items():
        if color_filter is not None and color not in color_filter:
            continue
        if not all(game_state.owners[t.position] is player for t in group):
            continue
        if any(game_state.mortgaged[t.position] for t in group):
            continue
        out.append(list(group))
    return out
