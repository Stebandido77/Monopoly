"""Strategy driven by a precomputed Markov + MILP board plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from monopoly.analytics.markov import build_transition_matrix, stationary_distribution
from monopoly.analytics.milp import MILPSolution, optimize_initial_purchase
from monopoly.strategies.base import JailAction, MortgageInheritance
from monopoly.strategies.cautious import CautiousStrategy

if TYPE_CHECKING:
    from monopoly.board import Board, Tile
    from monopoly.game import Game
    from monopoly.player import Player


@dataclass(frozen=True)
class _StrategyPlan:
    solution: MILPSolution
    target_level: dict[int, int]


_STANDARD_BOARD_SIGNATURE = (
    (0, "go", None, None),
    (1, "street", "brown", 60),
    (2, "community_chest", None, None),
    (3, "street", "brown", 60),
    (4, "tax", None, None),
    (5, "railroad", None, 200),
    (6, "street", "light_blue", 100),
    (7, "chance", None, None),
    (8, "street", "light_blue", 100),
    (9, "street", "light_blue", 120),
    (10, "jail", None, None),
    (11, "street", "pink", 140),
    (12, "utility", None, 150),
    (13, "street", "pink", 140),
    (14, "street", "pink", 160),
    (15, "railroad", None, 200),
    (16, "street", "orange", 180),
    (17, "community_chest", None, None),
    (18, "street", "orange", 180),
    (19, "street", "orange", 200),
    (20, "free_parking", None, None),
    (21, "street", "red", 220),
    (22, "chance", None, None),
    (23, "street", "red", 220),
    (24, "street", "red", 240),
    (25, "railroad", None, 200),
    (26, "street", "yellow", 260),
    (27, "street", "yellow", 260),
    (28, "utility", None, 150),
    (29, "street", "yellow", 280),
    (30, "go_to_jail", None, None),
    (31, "street", "green", 300),
    (32, "street", "green", 300),
    (33, "community_chest", None, None),
    (34, "street", "green", 320),
    (35, "railroad", None, 200),
    (36, "chance", None, None),
    (37, "street", "dark_blue", 350),
    (38, "tax", None, None),
    (39, "street", "dark_blue", 400),
)

_DEFAULT_STANDARD_PLAN = _StrategyPlan(
    solution=MILPSolution(
        purchase={
            1: False,
            3: False,
            6: False,
            8: False,
            9: False,
            11: False,
            13: False,
            14: False,
            16: True,
            18: True,
            19: True,
            21: False,
            23: False,
            24: False,
            26: False,
            27: False,
            29: False,
            31: False,
            32: False,
            34: False,
            37: False,
            39: False,
        },
        houses={
            1: 0,
            3: 0,
            6: 0,
            8: 0,
            9: 0,
            11: 0,
            13: 0,
            14: 0,
            16: 3,
            18: 3,
            19: 3,
            21: 0,
            23: 0,
            24: 0,
            26: 0,
            27: 0,
            29: 0,
            31: 0,
            32: 0,
            34: 0,
            37: 0,
            39: 0,
        },
        hotel={
            1: False,
            3: False,
            6: False,
            8: False,
            9: False,
            11: False,
            13: False,
            14: False,
            16: False,
            18: False,
            19: False,
            21: False,
            23: False,
            24: False,
            26: False,
            27: False,
            29: False,
            31: False,
            32: False,
            34: False,
            37: False,
            39: False,
        },
        expected_rent_per_turn=49.73911991276066,
        total_cost=1460,
        solver_status="Optimal",
    ),
    target_level={16: 3, 18: 3, 19: 3},
)


class MILPStrategy:
    """Play toward a cached MILP plan derived from stationary board traffic."""

    _PLAN_CACHE: ClassVar[
        dict[
            tuple[int, tuple[tuple[int, str, str | None, int | None], ...]],
            _StrategyPlan,
        ]
    ] = {}

    def __init__(self) -> None:
        self._fallback = CautiousStrategy()
        self._plan: _StrategyPlan | None = None
        self._budget_key: int | None = None

    def decide_purchase(self, player: Player, tile: Tile, game_state: Game) -> bool:
        self._ensure_plan(player, game_state)
        if tile.type != "street" or self._plan is None:
            return False
        return self._plan.solution.purchase.get(tile.position, False)

    def decide_jail_action(self, player: Player, game_state: Game) -> JailAction:
        self._ensure_plan(player, game_state)
        if player.jail_free_cards:
            return "card"
        pending = self._planned_purchases_remaining(player)
        if pending and player.cash > game_state.board.bank.jail_fine + 200:
            return "pay"
        return "roll"

    def decide_build(self, player: Player, game_state: Game) -> list[Tile]:
        self._ensure_plan(player, game_state)
        if self._plan is None:
            return self._fallback.decide_build(player, game_state)
        return _build_toward_targets(player, game_state, self._plan.target_level)

    def decide_mortgage(self, player: Player, game_state: Game) -> list[Tile]:
        if player.cash >= 0:
            return []
        self._ensure_plan(player, game_state)
        planned_positions = (
            set(self._plan.target_level) if self._plan is not None else set()
        )
        return sorted(
            [tile for tile in player.properties if not game_state.mortgaged[tile.position]],
            key=lambda tile: (
                tile.position in planned_positions,
                tile.mortgage_value or 0,
                tile.price or 0,
            ),
        )

    def decide_unmortgage(self, player: Player, game_state: Game) -> list[Tile]:
        return self._fallback.decide_unmortgage(player, game_state)

    def decide_inherited_mortgage(
        self, player: Player, tile: Tile, game_state: Game
    ) -> MortgageInheritance:
        return "keep_mortgaged"

    def _ensure_plan(self, player: Player, game_state: Game) -> None:
        if self._plan is not None:
            return

        budget = self._budget_key if self._budget_key is not None else player.cash
        self._budget_key = budget
        cache_key = (budget, _board_signature(game_state.board))
        cached = self._PLAN_CACHE.get(cache_key)
        if cached is not None:
            self._plan = cached
            return

        default_plan = _maybe_default_plan(game_state.board, budget)
        if default_plan is not None:
            self._plan = default_plan
            self._PLAN_CACHE[cache_key] = default_plan
            return

        stationary = stationary_distribution(build_transition_matrix(game_state.board))
        solution = optimize_initial_purchase(game_state.board, budget, stationary)
        target_level = {
            pos: 5 if solution.hotel.get(pos, False) else solution.houses.get(pos, 0)
            for pos, should_buy in solution.purchase.items()
            if should_buy
        }
        self._plan = _StrategyPlan(solution=solution, target_level=target_level)
        self._PLAN_CACHE[cache_key] = self._plan

    def _planned_purchases_remaining(self, player: Player) -> bool:
        if self._plan is None:
            return False
        owned_positions = {tile.position for tile in player.properties}
        return any(
            should_buy and position not in owned_positions
            for position, should_buy in self._plan.solution.purchase.items()
        )


def _build_toward_targets(
    player: Player,
    game_state: Game,
    target_level: dict[int, int],
) -> list[Tile]:
    chosen: list[Tile] = []
    sim_houses = dict(game_state.houses)
    sim_hotels = dict(game_state.hotels)
    sim_cash = player.cash
    sim_houses_avail = game_state.available_houses
    sim_hotels_avail = game_state.available_hotels

    owned_positions = {tile.position for tile in player.properties}
    eligible_groups: list[list[Tile]] = []
    for _color, group in game_state.board.color_groups.items():
        positions = {tile.position for tile in group}
        if not positions.intersection(target_level):
            continue
        if not positions.issubset(owned_positions):
            continue
        if any(game_state.mortgaged[tile.position] for tile in group):
            continue
        eligible_groups.append(list(group))

    if not eligible_groups:
        return []

    def current_level(tile: Tile) -> int:
        return 5 if sim_hotels[tile.position] else sim_houses[tile.position]

    while True:
        progress = False
        for group in eligible_groups:
            candidates = [
                tile
                for tile in group
                if current_level(tile) < target_level.get(tile.position, 0)
            ]
            if not candidates:
                continue

            tile = min(candidates, key=current_level)
            tile_cost = tile.house_cost
            if tile_cost is None or sim_cash < tile_cost:
                continue

            current = current_level(tile)
            target = target_level[tile.position]
            if current >= target:
                continue

            if current == 4 and target == 5:
                if sim_hotels_avail < 1 or any(current_level(t) < 4 for t in group):
                    continue
                chosen.append(tile)
                sim_cash -= tile_cost
                sim_hotels[tile.position] = True
                sim_houses[tile.position] = 0
                sim_houses_avail += 4
                sim_hotels_avail -= 1
                progress = True
                continue

            if sim_houses_avail < 1:
                continue

            new_level = current + 1
            other_levels = [
                new_level if other.position == tile.position else current_level(other)
                for other in group
            ]
            if max(other_levels) - min(other_levels) > 1:
                continue

            chosen.append(tile)
            sim_cash -= tile_cost
            sim_houses[tile.position] = new_level
            sim_houses_avail -= 1
            progress = True

        if not progress:
            break

    return chosen


def _board_signature(board: Board) -> tuple[tuple[int, str, str | None, int | None], ...]:
    return tuple(
        (tile.position, tile.type, tile.color_group, tile.price) for tile in board.tiles
    )


def _maybe_default_plan(board: Board, budget: int) -> _StrategyPlan | None:
    if budget != board.bank.starting_money:
        return None
    if _board_signature(board) != _STANDARD_BOARD_SIGNATURE:
        return None
    return _DEFAULT_STANDARD_PLAN
