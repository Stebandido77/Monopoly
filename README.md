# Monopoly Strategy Simulator

[![CI](https://github.com/Stebandido77/Monopoly/actions/workflows/ci.yml/badge.svg)](https://github.com/Stebandido77/Monopoly/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-TBD-lightgrey)](LICENSE)

Quantitative benchmark of Monopoly strategies for the standard US Hasbro board.
The project now combines a rules-based simulator, heuristic strategies,
Markov-chain board analytics, and a PuLP/CBC MILP optimizer that feeds a
playable strategy.

The legacy notebooks in `legacy/` are preserved as historical reference only.
The source of truth is the typed Python package in `src/monopoly/`, tested
against the current engine and official-rule behavior.

## Current Highlights

- Full rules engine for movement, buying, rent, monopolies, uniform building,
  32-house / 12-hotel bank inventory, mortgages, jail, Chance, Community Chest,
  and bankruptcy with creditor transfer.
- Markov analysis builds a 40x40 board transition matrix using real 2d6
  probabilities, Go-to-Jail routing, and expected movement-card effects.
- MILP optimizer chooses street purchases and development levels under a budget,
  maximizing stationary-probability-weighted rent.
- `MILPStrategy` precomputes a Markov + MILP plan and executes it during real
  games against heuristic strategies.
- Monte Carlo runner supports deterministic seeds, parquet persistence, CI, and
  Windows-safe default execution.

## Architecture

```text
src/monopoly/
  board.py                 Static board and bank config loaded from YAML
  cards.py                 Chance / Community Chest decks and effects
  player.py                Mutable player state
  game.py                  Stateful rules engine
  simulation.py            MonteCarloRunner and result persistence
  analytics/
    markov.py              Transition matrix and stationary distribution
    milp.py                PuLP/CBC initial allocation optimizer
  strategies/
    base.py                Strategy protocol
    cautious.py            Cash-buffered conservative policy
    aggressive.py          Buy/build aggressively
    targeted.py            Orange/red/yellow heuristic
    random_strategy.py     Random baseline
    random_aggressive.py   Randomized aggressive baseline
    milp_optimal.py        Markov + MILP playable strategy
```

Data lives in `data/board.yaml`, `data/chance_cards.yaml`, and
`data/community_chest_cards.yaml`. Tests live in `tests/`.

## Install

```powershell
.\.venv\Scripts\python -m pip install -e .
```

Core dependencies include `numpy`, `pandas`, `pyarrow`, `hypothesis`, `ruff`,
`pytest`, and `pulp>=2.7`.

## Run The Main Benchmark

PowerShell-friendly 200-game smoke benchmark:

```powershell
@'
from monopoly.simulation import MonteCarloRunner
from monopoly.strategies import (
    MILPStrategy,
    CautiousStrategy,
    AggressiveStrategy,
    TargetedStrategy,
)

runner = MonteCarloRunner([
    ("milp", MILPStrategy),
    ("cautious", CautiousStrategy),
    ("aggressive", AggressiveStrategy),
    ("targeted", TargetedStrategy),
], n_games=200, seed=42)

df = runner.run()
print(df.groupby("winner_strategy").size())
print(df[["winner_strategy", "turns", "end_reason"]].head())
'@ | .\.venv\Scripts\python -
```

Persist a larger run to parquet:

```powershell
@'
from monopoly.simulation import MonteCarloRunner
from monopoly.strategies import MILPStrategy, CautiousStrategy, AggressiveStrategy, TargetedStrategy

runner = MonteCarloRunner([
    ("milp", MILPStrategy),
    ("cautious", CautiousStrategy),
    ("aggressive", AggressiveStrategy),
    ("targeted", TargetedStrategy),
], n_games=1000, seed=42)

df = runner.run()
path = runner.persist(df)
print(df.groupby("winner_strategy").size())
print(path)
'@ | .\.venv\Scripts\python -
```

## Key Results

Latest validated smoke run:

```text
Strategies: milp, cautious, aggressive, targeted
Games: 200
Seed: 42
Runtime: 33.77s on Windows, default runner settings
Errors: 0

winner_strategy
aggressive     65
cautious      119
milp            8
targeted        8
```

The winner distribution is not catastrophically dominated by one strategy:
the largest share in this run is `59.5%`, below the `90%` sanity threshold.
This is a smoke baseline, not the final statistical benchmark.

Markov/MILP sanity results:

- The transition matrix is row-stochastic: each row sums to 1.
- The stationary distribution sums to 1 and is non-negative.
- Orange properties (`16`, `18`, `19`) are above the uniform average `1/40`.
- Jail (`10`) is above the uniform average.
- With the standard board and starting cash `$1500`, the MILP optimum targets
  the orange group:

```text
Buy: St. James Place, Tennessee Avenue, New York Avenue
Build target: 3 houses on each orange property
Total planned cost: 1460
Expected rent per turn objective: 49.7391
Solver status: Optimal
```

## Quality Gate

Validated locally after the Markov + MILP + strategy integration:

```text
ruff check src tests
All checks passed

pytest -q --basetemp C:\tmp\pytest-monopoly
203 passed in 80.98s
```

GitHub Actions CI is green on `main` for the delivered Phase 3B commits.

## Notes For Windows

`MonteCarloRunner(n_workers=-1)` automatically uses in-process execution on
Windows. This avoids heavy `multiprocessing` spawn overhead for normal runs.
Explicit values such as `n_workers=4` still exercise the multiprocessing path
when needed.
