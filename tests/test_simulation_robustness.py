"""Robustness tests for :class:`monopoly.simulation.MonteCarloRunner`.

These tests cover the failure modes that caused a 1000-game benchmark to
hang on Windows: unpicklable factories (lambdas / closures), strategies
that raise mid-game, and the parallel-execution path under stress.

The :class:`FailingStrategy` and the helper functions defined at module
scope are deliberately top-level so they pickle cleanly across worker
processes.
"""

from __future__ import annotations

import time

import pandas as pd

from monopoly.simulation import MonteCarloRunner
from monopoly.strategies import (
    AggressiveStrategy,
    CautiousStrategy,
    RandomStrategy,
    TargetedStrategy,
)
from monopoly.strategies.base import JailAction

FACTORIES_FOUR = [
    ("cautious", CautiousStrategy),
    ("aggressive", AggressiveStrategy),
    ("targeted", TargetedStrategy),
    ("random", RandomStrategy),
]


# ---- Top-level helpers (must be picklable) --------------------------------


class FailingStrategy:
    """Top-level strategy that raises on every purchase decision.

    Used to verify that an exception inside a worker becomes
    ``end_reason="error"`` instead of stalling the run.
    """

    def decide_purchase(self, player, tile, game_state):
        raise RuntimeError("FailingStrategy.decide_purchase boom")

    def decide_jail_action(self, player, game_state) -> JailAction:
        return "roll"


def make_cautious() -> CautiousStrategy:
    """Top-level factory function — picklable, unlike a lambda."""
    return CautiousStrategy()


# ---- Factory validation ---------------------------------------------------


def test_factory_with_lambda_raises():
    """Lambdas are unpicklable; the runner must reject them at __init__."""
    import pytest

    with pytest.raises(TypeError, match="picklable"):
        MonteCarloRunner(
            [("bad", lambda: CautiousStrategy())],  # noqa: E731
            n_games=1,
            seed=0,
            n_workers=1,
        )


def test_top_level_function_factory_works():
    """A top-level function factory is fine — it picks up cleanly."""
    runner = MonteCarloRunner(
        [("cautious", make_cautious)],
        n_games=2,
        seed=0,
        n_workers=1,
    )
    df = runner.run()
    assert len(df) == 2


def test_factory_with_local_class_raises():
    """A class defined inside a function is unpicklable."""
    import pytest

    class _LocalStrategy:  # noqa: N801 — intentional local for the test
        def decide_purchase(self, player, tile, game_state):
            return False

        def decide_jail_action(self, player, game_state):
            return "roll"

    with pytest.raises(TypeError, match="picklable"):
        MonteCarloRunner(
            [("local", _LocalStrategy)],
            n_games=1,
            seed=0,
            n_workers=1,
        )


# ---- Worker exception handling --------------------------------------------


def test_runner_handles_strategy_exception_single_worker():
    """A strategy that raises does not stall the run; the row reports error."""
    factories = [
        ("good", CautiousStrategy),
        ("bad", FailingStrategy),
    ]
    runner = MonteCarloRunner(factories, n_games=10, seed=0, n_workers=1)
    df = runner.run()
    assert len(df) == 10
    assert (df["end_reason"] == "error").all()
    assert df["error"].notna().all()
    assert df["error"].str.contains("FailingStrategy.decide_purchase boom").all()


def test_runner_handles_strategy_exception_multi_worker():
    """Same isolation property under multiprocessing."""
    factories = [
        ("good", CautiousStrategy),
        ("bad", FailingStrategy),
    ]
    runner = MonteCarloRunner(factories, n_games=8, seed=0, n_workers=2)
    df = runner.run()
    assert len(df) == 8
    assert (df["end_reason"] == "error").all()


# ---- Performance ----------------------------------------------------------


def test_runner_500_games_completes_under_60s():
    """A 500-game multi-worker run should finish well under the 60s budget.

    The previous failure mode was a fork-bomb hang in user scripts that
    forgot the ``if __name__ == "__main__":`` guard. The runner itself,
    when invoked correctly (this test is run by pytest, which is a
    properly-guarded entry point), must stay comfortably under wall-clock
    budget.
    """
    runner = MonteCarloRunner(FACTORIES_FOUR, n_games=500, seed=42, n_workers=4)
    t0 = time.perf_counter()
    df = runner.run()
    elapsed = time.perf_counter() - t0
    assert len(df) == 500
    assert elapsed < 60, f"500-game run took {elapsed:.1f}s (budget: 60s)"


# ---- Fork-bomb defense ----------------------------------------------------


def test_construction_inside_worker_raises(monkeypatch):
    """If __init__ is reached from a worker process, refuse to construct.

    This is the chain-breaker for the Windows-spawn fork bomb that
    happens when the user forgets ``if __name__ == "__main__":``: the
    spawned worker re-imports the launcher module, which would otherwise
    re-instantiate a runner and recursively spawn more pools.
    """
    import multiprocessing

    import pytest

    # Pretend we're inside a worker by faking a non-None parent.
    class FakeParent:
        pass

    monkeypatch.setattr(multiprocessing, "parent_process", lambda: FakeParent())
    with pytest.raises(RuntimeError, match="__main__"):
        MonteCarloRunner(
            [("cautious", CautiousStrategy)],
            n_games=1,
            seed=0,
            n_workers=1,
        )


# ---- Reproducibility under imap_unordered --------------------------------


def test_imap_unordered_preserves_seed_reproducibility():
    """Out-of-order delivery doesn't break determinism.

    Each game's outcome depends only on its (fixed-at-construction)
    per-game seed, not on which worker happens to pick it up or in what
    order results return. After sorting by ``game_id`` the two runs must
    be byte-identical.
    """
    r1 = MonteCarloRunner(FACTORIES_FOUR, n_games=20, seed=42, n_workers=4)
    r2 = MonteCarloRunner(FACTORIES_FOUR, n_games=20, seed=42, n_workers=4)
    df1 = r1.run()
    df2 = r2.run()
    pd.testing.assert_frame_equal(df1, df2)
