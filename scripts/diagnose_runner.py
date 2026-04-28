#!/usr/bin/env python
"""Diagnose MonteCarloRunner under multiprocessing on Windows.

Runs four escalating tests, each with its own per-test wall-clock fence
implemented at the script level (we measure elapsed time and abort the
escalation if a step exceeds ``SOFT_TIMEOUT_S``). The output line for
each test tells you exactly where execution got stuck:

    Test 1 — single-worker baseline. If this fails, the engine itself
             is broken; multiprocessing is not the cause.
    Test 2 — small parallel run (10 games, 4 workers). If this hangs
             but Test 1 completed, the multiprocessing setup is broken
             (the most common Windows cause is a missing
             ``if __name__ == "__main__":`` guard at the call site).
    Test 3 — 100 games, 4 workers. If this hangs but Test 2 passed,
             suspect chunksize or per-game stalls.
    Test 4 — 500 games, 4 workers. Stress test for steady-state
             throughput.

Run:

    python scripts/diagnose_runner.py
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable

SOFT_TIMEOUT_S = 60.0  # If a test exceeds this we abort the whole script.


def _time_step(label: str, fn: Callable[[], int]) -> bool:
    """Run ``fn``, print elapsed wall-clock; abort if over SOFT_TIMEOUT_S."""
    print(f"=== {label} ===", flush=True)
    t0 = time.perf_counter()
    try:
        n_rows = fn()
    except Exception as exc:  # noqa: BLE001 — diagnostic output
        elapsed = time.perf_counter() - t0
        print(f"FAIL ({elapsed:.1f}s): {type(exc).__name__}: {exc}", flush=True)
        return False
    elapsed = time.perf_counter() - t0
    if elapsed > SOFT_TIMEOUT_S:
        print(
            f"SLOW ({elapsed:.1f}s, {n_rows} rows) — exceeded {SOFT_TIMEOUT_S:.0f}s soft limit",
            flush=True,
        )
        return False
    print(f"OK ({elapsed:.1f}s, {n_rows} rows)", flush=True)
    return True


if __name__ == "__main__":
    # Imports inside __main__ so a child process re-importing this module
    # under spawn does NOT pay the import cost or run any code.
    from monopoly.simulation import MonteCarloRunner
    from monopoly.strategies import (
        AggressiveStrategy,
        CautiousStrategy,
        RandomStrategy,
        TargetedStrategy,
    )

    factories = [
        ("cautious", CautiousStrategy),
        ("aggressive", AggressiveStrategy),
        ("targeted", TargetedStrategy),
        ("random", RandomStrategy),
    ]

    def run_case(n_games: int, n_workers: int) -> int:
        runner = MonteCarloRunner(
            factories, n_games=n_games, seed=42, n_workers=n_workers
        )
        df = runner.run()
        return len(df)

    steps = [
        ("Test 1: 10 games, n_workers=1", lambda: run_case(10, 1)),
        ("Test 2: 10 games, n_workers=4", lambda: run_case(10, 4)),
        ("Test 3: 100 games, n_workers=4", lambda: run_case(100, 4)),
        ("Test 4: 500 games, n_workers=4", lambda: run_case(500, 4)),
    ]

    for label, fn in steps:
        if not _time_step(label, fn):
            print(f"\nAbort: stopped at '{label}'", flush=True)
            sys.exit(1)

    print("\n=== Diagnose complete: all 4 stages passed ===", flush=True)
