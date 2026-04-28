# Monopoly Strategy Simulator

[![CI](https://img.shields.io/badge/CI-pending-lightgrey)](.github/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-TBD-lightgrey)](LICENSE)

> **Status: under reconstruction.** The legacy notebooks (`Monopoly.ipynb`, `Monopoly_V2.ipynb`, `Modelos de optimizacion estocastico.ipynb`) are preserved for historical reference but are being replaced by a properly structured Python package. Project governance lives in `.claude/CLAUDE.md`.

Quantitative benchmark of strategies for Monopoly (Hasbro standard US edition). The project compares heuristic policies, MILP-derived allocations, simulated annealing solutions, and Markov-chain-guided strategies through Monte Carlo simulation, producing statistical comparisons with confidence intervals suitable for a working paper.

This repository is undergoing a full refactor from the original Jupyter notebooks into a reproducible Python package (`src/monopoly/`) with type hints, official-rules-based unit tests, deterministic seeding, and CI. Reproducibility, correctness against the official Hasbro ruleset, and a clean separation between simulation engine, strategies, and analysis are the design priorities.
