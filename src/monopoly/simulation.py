"""Monte Carlo simulation harness for Monopoly strategy benchmarks.

Runs a configurable bag of strategies over many independent games. The
seeding plan is fixed up front using :class:`numpy.random.SeedSequence` —
the master seed spawns one child sequence per game, and each child becomes
a 32-bit integer seed for that game's :class:`monopoly.game.Game`. As a
consequence, the worker count never affects results: a 1000-game run
produces the same DataFrame whether executed in one process or forty.

Parallelization uses ``multiprocessing.Pool.imap_unordered`` with a
chunksize tuned for the run, and every worker call is wrapped in a
top-level safe handler so a single failing game cannot stall the pool —
the offending game is reported with ``end_reason="error"`` and the run
proceeds.

Persistence writes a parquet file with the run's git-hash, the package
version, the timestamp, and a JSON-encoded snapshot of the runner
parameters embedded in the schema metadata.

Windows usage note
------------------

On Windows the ``multiprocessing`` start method is ``spawn``: every
worker re-imports the script that launched it. Calling
:meth:`MonteCarloRunner.run` from un-guarded module-level code therefore
re-creates the runner — and another Pool — in every worker, recursively
spawning processes until the OS runs out of resources (a fork bomb that
locks up the terminal and cannot be Ctrl+C-killed). Always wrap the
launch in an ``if __name__ == "__main__":`` guard:

.. code-block:: python

    from monopoly.simulation import MonteCarloRunner
    from monopoly.strategies import CautiousStrategy, AggressiveStrategy

    if __name__ == "__main__":
        runner = MonteCarloRunner(
            strategy_factories=[
                ("cautious", CautiousStrategy),
                ("aggressive", AggressiveStrategy),
            ],
            n_games=1000,
            seed=42,
            n_workers=4,
        )
        df = runner.run()

The runner detects construction inside a worker process at ``__init__``
and raises :class:`RuntimeError` to break the recursion early, but the
guard is still the right answer.
"""

from __future__ import annotations

import importlib.metadata
import json
import multiprocessing
import os
import pickle
import subprocess
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from multiprocessing import Pool
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from monopoly.board import Board
from monopoly.game import Game
from monopoly.player import Player

if TYPE_CHECKING:
    from monopoly.strategies.base import Strategy


StrategyFactory = Callable[[], "Strategy"]
EndReason = Literal["bankruptcy", "timeout", "error"]


@dataclass
class GameResult:
    """One game's terminal state, ready to flatten into a DataFrame row.

    All ``dict[str, int]`` fields are keyed by ``strategy_name`` (the
    same string used in :class:`MonteCarloRunner.strategy_factories`).
    ``end_reason="error"`` indicates the game raised an unhandled
    exception inside the worker; the message is captured in ``error``
    and the numeric fields are zeroed out.
    """

    game_id: int
    seed: int
    winner_strategy: str | None
    winner_index: int | None
    turns: int
    end_reason: EndReason
    final_net_worth: dict[str, int]
    final_cash: dict[str, int]
    n_properties: dict[str, int]
    n_houses: dict[str, int]
    n_hotels: dict[str, int]
    error: str | None = field(default=None)


class MonteCarloRunner:
    """Configure and execute a bag of independent Monopoly games.

    Parameters
    ----------
    strategy_factories : list[tuple[str, Callable[[], Strategy]]]
        Each factory creates a fresh Strategy per game (so internal state
        does not leak across games). The string is both the player name
        and the column suffix in the output DataFrame; names must be
        unique within a runner.
    n_games : int
        Number of games to run.
    max_turns : int
        Outer-loop cap per game. A game that does not terminate by
        bankruptcy within this many rounds is recorded with
        ``end_reason="timeout"``.
    starting_cash : int
        Initial cash per player. Defaults to the Hasbro $1500.
    seed : int or None
        Master seed. ``None`` uses system entropy (non-reproducible).
    n_workers : int
        Number of multiprocessing workers. ``-1`` selects an automatic
        default: on Windows it stays in-process to avoid ``spawn`` overhead
        for everyday runs, while on other platforms it uses every available
        core. ``1`` always keeps everything in-process.
    board_path : str or None
        Path to the board YAML. ``None`` loads the bundled default.
    """

    def __init__(
        self,
        strategy_factories: list[tuple[str, StrategyFactory]],
        n_games: int,
        max_turns: int = 1000,
        starting_cash: int = 1500,
        seed: int | None = None,
        n_workers: int = -1,
        board_path: str | None = None,
    ) -> None:
        # Refuse construction inside an already-spawned multiprocessing worker.
        # If the user's launching script lacks ``if __name__ == "__main__":``,
        # every worker re-imports it and re-runs the runner construction,
        # which then spawns its own Pool — recursively, ad infinitum. We break
        # the chain here with a clear error before any further workers spawn.
        if multiprocessing.parent_process() is not None:
            raise RuntimeError(
                "MonteCarloRunner is being constructed inside a multiprocessing "
                "worker. Wrap the launching script's top-level code in an "
                '`if __name__ == "__main__":` guard. On Windows (spawn start '
                "method), unguarded module-level code is re-executed in every "
                "worker, which would recursively spawn more pools and exhaust "
                "system resources."
            )

        names = [n for n, _ in strategy_factories]
        if len(set(names)) != len(names):
            raise ValueError("Strategy names must be unique within a runner.")
        if n_games < 1:
            raise ValueError("n_games must be >= 1")

        self.strategy_factories: list[tuple[str, StrategyFactory]] = list(
            strategy_factories
        )

        # Validate the factories are picklable. Lambdas, closures, and bound
        # methods are not — and in multiprocessing they would either fail at
        # dispatch or, worse, hang the workers silently. Catch this eagerly so
        # the diagnostic points at the offending factory rather than at a
        # cryptic Pool error.
        for name, factory in self.strategy_factories:
            try:
                pickle.dumps(factory)
            except (pickle.PicklingError, AttributeError, TypeError) as exc:
                raise TypeError(
                    f"Strategy factory for {name!r} is not picklable "
                    f"({type(factory).__name__}: {factory!r}). Use a top-level "
                    "class or function — lambdas, closures, and bound methods "
                    "cannot cross multiprocessing worker boundaries. "
                    f"Underlying pickle error: {exc}"
                ) from exc

        self.n_games = int(n_games)
        self.max_turns = int(max_turns)
        self.starting_cash = int(starting_cash)
        self.seed = seed
        self.n_workers = int(n_workers)
        self.board_path = board_path

        # Pre-spawn child SeedSequences so the seed plan is fixed.
        master = np.random.SeedSequence(seed)
        self._game_seeds: list[int] = [
            int(child.generate_state(1, dtype=np.uint32)[0])
            for child in master.spawn(self.n_games)
        ]

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self) -> pd.DataFrame:
        """Execute all games and return a flattened DataFrame (one row per game).

        Uses :meth:`Pool.imap_unordered` with a chunksize sized to the run
        (``max(1, n_games // (n_workers * 4))``) so results stream back as
        they complete and chunk overhead stays low. Out-of-order delivery
        is fine: the per-game seed is fixed at construction, so the
        outcome of each row depends only on its seed, and
        :meth:`_results_to_df` sorts by ``game_id`` before returning.

        Each worker call goes through :func:`_run_one_game_safe`, which
        catches any exception raised inside a game and converts it to a
        :class:`GameResult` with ``end_reason="error"``. A failing game
        therefore cannot stall the pool.
        """
        n_workers = self._resolve_workers()
        args = [
            (
                game_id,
                self._game_seeds[game_id],
                self.strategy_factories,
                self.max_turns,
                self.starting_cash,
                self.board_path,
            )
            for game_id in range(self.n_games)
        ]
        if n_workers <= 1:
            results = [_run_one_game_safe(a) for a in args]
        else:
            chunksize = max(1, self.n_games // (n_workers * 4))
            with Pool(processes=n_workers) as pool:
                results = list(
                    pool.imap_unordered(
                        _run_one_game_safe, args, chunksize=chunksize
                    )
                )
        return self._results_to_df(results)

    def persist(
        self, df: pd.DataFrame, output_dir: str = "data/results"
    ) -> Path:
        """Write ``df`` to parquet with run metadata embedded in the schema.

        The filename is ``{YYYYMMDD_HHMMSS}_{git_short_hash}.parquet``,
        UTC. Metadata keys: ``package_version``, ``git_hash``,
        ``timestamp``, ``params`` (JSON of the runner parameters).
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        git_short = _git_short_hash()
        path = out / f"{timestamp}_{git_short}.parquet"
        table = pa.Table.from_pandas(df)
        meta_new = {
            b"package_version": _package_version().encode(),
            b"git_hash": _git_hash().encode(),
            b"timestamp": timestamp.encode(),
            b"params": json.dumps(self._params_dict()).encode(),
        }
        existing = dict(table.schema.metadata or {})
        existing.update(meta_new)
        table = table.replace_schema_metadata(existing)
        pq.write_table(table, path)
        return path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_workers(self) -> int:
        if self.n_workers == -1:
            if os.name == "nt":
                return 1
            return os.cpu_count() or 1
        return max(1, self.n_workers)

    def _params_dict(self) -> dict[str, Any]:
        return {
            "n_games": self.n_games,
            "max_turns": self.max_turns,
            "starting_cash": self.starting_cash,
            "seed": self.seed,
            "n_workers": self.n_workers,
            "board_path": self.board_path,
            "strategy_names": [n for n, _ in self.strategy_factories],
        }

    def _results_to_df(self, results: list[GameResult]) -> pd.DataFrame:
        names = [n for n, _ in self.strategy_factories]
        rows: list[dict[str, Any]] = []
        for r in results:
            row: dict[str, Any] = {
                "game_id": r.game_id,
                "seed": r.seed,
                "winner_strategy": r.winner_strategy,
                "winner_index": r.winner_index,
                "turns": r.turns,
                "end_reason": r.end_reason,
                "error": r.error,
            }
            for n in names:
                row[f"final_net_worth_{n}"] = r.final_net_worth.get(n, 0)
                row[f"final_cash_{n}"] = r.final_cash.get(n, 0)
                row[f"n_properties_{n}"] = r.n_properties.get(n, 0)
                row[f"n_houses_{n}"] = r.n_houses.get(n, 0)
                row[f"n_hotels_{n}"] = r.n_hotels.get(n, 0)
            rows.append(row)
        df = pd.DataFrame(rows)
        df = df.sort_values("game_id").reset_index(drop=True)
        return df


# ----------------------------------------------------------------------
# Worker (top-level so it pickles for multiprocessing.Pool)
# ----------------------------------------------------------------------


def _run_one_game_safe(
    args: tuple[
        int,
        int,
        list[tuple[str, StrategyFactory]],
        int,
        int,
        str | None,
    ],
) -> GameResult:
    """Safe wrapper around :func:`_run_one_game`.

    Any exception raised inside the game (a buggy strategy, a corrupted
    board file, etc.) is caught and rendered as a ``GameResult`` with
    ``end_reason="error"`` and the exception summary in ``error``. This
    keeps the Pool draining: a single failure cannot deadlock or stall
    the whole run.
    """
    try:
        return _run_one_game(args)
    except Exception as exc:  # noqa: BLE001 — boundary catch for worker
        game_id, seed, factories, _, _, _ = args
        names = [n for n, _ in factories]
        zeroed = {n: 0 for n in names}
        return GameResult(
            game_id=game_id,
            seed=seed,
            winner_strategy=None,
            winner_index=None,
            turns=0,
            end_reason="error",
            final_net_worth=dict(zeroed),
            final_cash=dict(zeroed),
            n_properties=dict(zeroed),
            n_houses=dict(zeroed),
            n_hotels=dict(zeroed),
            error=f"{type(exc).__name__}: {exc}\n"
            + "".join(traceback.format_exception(exc))[:1000],
        )


def _run_one_game(
    args: tuple[
        int,
        int,
        list[tuple[str, StrategyFactory]],
        int,
        int,
        str | None,
    ],
) -> GameResult:
    """Run a single game and return its terminal state.

    Module-level function so :class:`multiprocessing.Pool` can pickle it.
    The args tuple matches what :meth:`MonteCarloRunner.run` builds.
    """
    game_id, seed, factories, max_turns, starting_cash, board_path = args
    board = Board.default() if board_path is None else Board.from_yaml(board_path)
    players = [Player(name, cash=starting_cash) for name, _ in factories]
    strategies = {name: factory() for name, factory in factories}
    game = Game(players, board, strategies=strategies, seed=seed)

    turns_played = 0
    end_reason: EndReason = "timeout"
    for _ in range(max_turns):
        survivors = [p for p in game.players if p.cash >= 0]
        if len(survivors) <= 1:
            end_reason = "bankruptcy"
            break
        for player in game.players:
            if player.cash < 0:
                continue
            game.play_turn(player)
        turns_played += 1

    survivors = [p for p in game.players if p.cash >= 0]
    if not survivors:
        winner = None
    elif len(survivors) == 1:
        winner = survivors[0]
    else:
        winner = max(survivors, key=lambda p: _net_worth(p, game))

    if winner is not None:
        winner_strategy: str | None = winner.name
        winner_index: int | None = next(
            i for i, (n, _) in enumerate(factories) if n == winner.name
        )
    else:
        winner_strategy = None
        winner_index = None

    return GameResult(
        game_id=game_id,
        seed=seed,
        winner_strategy=winner_strategy,
        winner_index=winner_index,
        turns=turns_played,
        end_reason=end_reason,
        final_net_worth={p.name: _net_worth(p, game) for p in players},
        final_cash={p.name: p.cash for p in players},
        n_properties={p.name: len(p.properties) for p in players},
        n_houses={
            p.name: sum(
                game.houses[t.position] for t in p.properties if t.type == "street"
            )
            for p in players
        },
        n_hotels={
            p.name: sum(
                1
                for t in p.properties
                if t.type == "street" and game.hotels[t.position]
            )
            for p in players
        },
    )


def _net_worth(player: Player, game: Game) -> int:
    """Cash + property face/mortgage value + buildings at full cost.

    A bankrupt player (``cash < 0``, properties already cleared) is reported
    as 0 so downstream aggregations are well-behaved.
    """
    if player.cash < 0:
        return 0
    nw = player.cash
    for tile in player.properties:
        if game.mortgaged[tile.position]:
            nw += tile.mortgage_value or 0
        else:
            nw += tile.price or 0
        if tile.type == "street":
            houses = game.houses[tile.position]
            nw += houses * (tile.house_cost or 0)
            if game.hotels[tile.position]:
                nw += 5 * (tile.house_cost or 0)
    return nw


# ----------------------------------------------------------------------
# Provenance helpers
# ----------------------------------------------------------------------


def _git_hash() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"


def _git_short_hash() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"


def _package_version() -> str:
    try:
        return importlib.metadata.version("monopoly")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"
