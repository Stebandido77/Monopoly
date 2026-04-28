"""Tests for :class:`monopoly.simulation.MonteCarloRunner`.

Reproducibility, parallelization determinism, output schema, and parquet
persistence with embedded provenance metadata.
"""

from __future__ import annotations

import json

import pandas as pd
import pyarrow.parquet as pq
import pytest

from monopoly.simulation import GameResult, MonteCarloRunner
from monopoly.strategies import (
    AggressiveStrategy,
    CautiousStrategy,
    RandomStrategy,
    TargetedStrategy,
)

FACTORIES_FOUR = [
    ("cautious", CautiousStrategy),
    ("aggressive", AggressiveStrategy),
    ("targeted", TargetedStrategy),
    ("random", RandomStrategy),
]


# --- API & schema -----------------------------------------------------------


def test_run_returns_one_row_per_game():
    runner = MonteCarloRunner(FACTORIES_FOUR, n_games=8, seed=42, n_workers=1)
    df = runner.run()
    assert len(df) == 8


def test_run_columns_present_for_each_strategy():
    runner = MonteCarloRunner(FACTORIES_FOUR, n_games=3, seed=42, n_workers=1)
    df = runner.run()
    base = {"game_id", "seed", "winner_strategy", "winner_index", "turns", "end_reason"}
    assert base.issubset(df.columns)
    for name, _ in FACTORIES_FOUR:
        for stat in (
            "final_net_worth",
            "final_cash",
            "n_properties",
            "n_houses",
            "n_hotels",
        ):
            assert f"{stat}_{name}" in df.columns


def test_winner_index_matches_strategy_position():
    runner = MonteCarloRunner(FACTORIES_FOUR, n_games=20, seed=42, n_workers=1)
    df = runner.run()
    names = [n for n, _ in FACTORIES_FOUR]
    for _, row in df.iterrows():
        if pd.isna(row["winner_strategy"]):
            assert pd.isna(row["winner_index"])
        else:
            assert names[int(row["winner_index"])] == row["winner_strategy"]


def test_unique_strategy_names_required():
    with pytest.raises(ValueError, match="unique"):
        MonteCarloRunner(
            [("a", CautiousStrategy), ("a", AggressiveStrategy)],
            n_games=1,
            seed=0,
        )


def test_n_games_positive():
    with pytest.raises(ValueError, match=">= 1"):
        MonteCarloRunner([("a", CautiousStrategy)], n_games=0, seed=0)


# --- reproducibility --------------------------------------------------------


def test_same_seed_produces_identical_dataframes():
    """Two runs with the same master seed must produce identical DataFrames."""
    r1 = MonteCarloRunner(FACTORIES_FOUR, n_games=15, seed=42, n_workers=1)
    r2 = MonteCarloRunner(FACTORIES_FOUR, n_games=15, seed=42, n_workers=1)
    pd.testing.assert_frame_equal(r1.run(), r2.run())


def test_different_seeds_diverge():
    """Sanity: different master seeds produce different game seeds."""
    r1 = MonteCarloRunner(FACTORIES_FOUR, n_games=10, seed=42, n_workers=1)
    r2 = MonteCarloRunner(FACTORIES_FOUR, n_games=10, seed=7, n_workers=1)
    df1 = r1.run()
    df2 = r2.run()
    assert not df1["seed"].equals(df2["seed"])


# --- parallelization determinism --------------------------------------------


def test_workers_one_vs_two_match():
    """Per-game seeds are fixed at construction; worker count cannot change them."""
    r1 = MonteCarloRunner(FACTORIES_FOUR, n_games=12, seed=42, n_workers=1)
    r2 = MonteCarloRunner(FACTORIES_FOUR, n_games=12, seed=42, n_workers=2)
    df1 = r1.run()
    df2 = r2.run()
    pd.testing.assert_frame_equal(df1, df2)


# --- end-to-end smoke -------------------------------------------------------


def test_50_games_runs_without_exceptions():
    runner = MonteCarloRunner(FACTORIES_FOUR, n_games=50, seed=42, n_workers=1)
    df = runner.run()
    assert len(df) == 50
    # Most games complete by bankruptcy or hit the timeout — both are valid.
    assert set(df["end_reason"]).issubset({"bankruptcy", "timeout"})


# --- persistence ------------------------------------------------------------


def test_persist_creates_parquet_with_metadata(tmp_path):
    runner = MonteCarloRunner(
        FACTORIES_FOUR, n_games=5, seed=42, n_workers=1
    )
    df = runner.run()
    path = runner.persist(df, output_dir=str(tmp_path))
    assert path.exists()
    assert path.suffix == ".parquet"
    table = pq.read_table(path)
    df_back = table.to_pandas()
    assert len(df_back) == 5
    metadata = dict(table.schema.metadata or {})
    for key in (b"git_hash", b"package_version", b"timestamp", b"params"):
        assert key in metadata
    params = json.loads(metadata[b"params"].decode())
    assert params["n_games"] == 5
    assert params["seed"] == 42
    assert params["strategy_names"] == [n for n, _ in FACTORIES_FOUR]


def test_persist_filename_format(tmp_path):
    runner = MonteCarloRunner(
        [("a", CautiousStrategy)], n_games=1, seed=0, n_workers=1
    )
    df = runner.run()
    path = runner.persist(df, output_dir=str(tmp_path))
    # Filename: {YYYYMMDD_HHMMSS}_{git_short}.parquet
    stem = path.stem
    assert "_" in stem
    timestamp_part, _ = stem.split("_", 1)
    # date part is 8 digits, time part is HHMMSS — combined the leading
    # token before the FIRST underscore is YYYYMMDD.
    assert len(timestamp_part) == 8
    assert timestamp_part.isdigit()


def test_persist_roundtrip_preserves_columns(tmp_path):
    runner = MonteCarloRunner(FACTORIES_FOUR, n_games=4, seed=42, n_workers=1)
    df = runner.run()
    path = runner.persist(df, output_dir=str(tmp_path))
    df_back = pd.read_parquet(path)
    assert list(df_back.columns) == list(df.columns)
    pd.testing.assert_frame_equal(
        df_back.reset_index(drop=True), df.reset_index(drop=True)
    )


# --- GameResult dataclass ---------------------------------------------------


def test_game_result_is_dataclass_with_expected_fields():
    fields = {
        "game_id",
        "seed",
        "winner_strategy",
        "winner_index",
        "turns",
        "end_reason",
        "final_net_worth",
        "final_cash",
        "n_properties",
        "n_houses",
        "n_hotels",
    }
    actual = {f.name for f in GameResult.__dataclass_fields__.values()}
    assert actual == fields
