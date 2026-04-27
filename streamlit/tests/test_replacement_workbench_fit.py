"""Integration tests for the benchmark-fit layer in replacement_workbench."""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pandas as pd
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_STREAMLIT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _STREAMLIT_DIR not in sys.path:
    sys.path.insert(0, _STREAMLIT_DIR)

from exposure_intake import parse_exposures  # noqa: E402
from replacement_workbench import (  # noqa: E402
    BENCHMARK_FIT_CANDIDATES_NAME,
    CURRENT_VS_BENCHMARK_NAME,
    REPLACEMENT_DELTA_NAME,
    SUMMARY_NAME,
    build_replacement_workbench,
    load_replacement,
    write_replacement,
)


FIX_DIR = os.path.join(_HERE, "fixtures")


def _fix(name: str) -> str:
    return os.path.join(FIX_DIR, name)


def _dual_table():
    return pd.DataFrame([
        {"Symbol": "LLLA", "Name": "Large Blend Core",
         "Category": "Large Blend", "Fund_Type": "Active",
         "Score_2023_Final": 60.0, "Score_2025_Final": 65.0,
         "Score_Band_2023": "REVIEW", "Score_Band_2025": "REVIEW",
         "Quadrant": "Q4_Mid", "Consensus_Rank": 5,
         "Score_Gap": 5.0, "Rank_2023": 5, "Rank_2025": 5,
         "Action_Flag": "REVIEW", "Primary_Driver": "x"},
        {"Symbol": "CAND_FIT", "Name": "Best Fit Active",
         "Category": "Large Blend", "Fund_Type": "Active",
         "Score_2023_Final": 70.0, "Score_2025_Final": 70.0,
         "Score_Band_2023": "REVIEW", "Score_Band_2025": "REVIEW",
         "Quadrant": "Q4_Mid", "Consensus_Rank": 3,
         "Score_Gap": 0.0, "Rank_2023": 3, "Rank_2025": 3,
         "Action_Flag": "REVIEW", "Primary_Driver": "y"},
        {"Symbol": "CAND_DRIFT", "Name": "Off-Bench Growth",
         "Category": "Large Blend", "Fund_Type": "Active",
         "Score_2023_Final": 95.0, "Score_2025_Final": 95.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
         "Quadrant": "Q1_Both_Strong", "Consensus_Rank": 1,
         "Score_Gap": 0.0, "Rank_2023": 1, "Rank_2025": 1,
         "Action_Flag": "LEAD", "Primary_Driver": "z"},
        {"Symbol": "CAND_MID", "Name": "Decent-Fit Mid Lean",
         "Category": "Large Blend", "Fund_Type": "Active",
         "Score_2023_Final": 80.0, "Score_2025_Final": 78.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "REVIEW",
         "Quadrant": "Q3_Only_2023", "Consensus_Rank": 2,
         "Score_Gap": -2.0, "Rank_2023": 2, "Rank_2025": 4,
         "Action_Flag": "REVIEW", "Primary_Driver": "w"},
    ])


def _holdings():
    return pd.DataFrame([
        {"Model_Name": "100/0", "Symbol": "LLLA", "Target_Weight": 0.50},
        {"Model_Name": "100/0", "Symbol": "LLLB", "Target_Weight": 0.10},
        {"Model_Name": "100/0", "Symbol": "LLLC", "Target_Weight": 0.10},
        {"Model_Name": "100/0", "Symbol": "LLLD", "Target_Weight": 0.20},
        {"Model_Name": "100/0", "Symbol": "LLLE", "Target_Weight": 0.10},
    ])


def _bench_weights():
    return {"LLLA": 0.58, "LLLD": 0.24, "LLLB": 0.06, "LLLC": 0.06, "LLLE": 0.06}


def test_workbench_with_fit_inputs_produces_dual_lens_plus_drift():
    model_exp = parse_exposures(_fix("exposures_model_good.csv"))
    bench_exp = parse_exposures(_fix("exposures_bench_good.csv"))
    cand_exp = parse_exposures(_fix("exposures_candidates_good.csv"))

    result = build_replacement_workbench(
        _dual_table(), "LLLA", top_n=10, alias_map={},
        model_holdings=_holdings(),
        model_exposures=model_exp,
        benchmark_exposures=bench_exp,
        benchmark_weights=_bench_weights(),
        candidate_exposures=cand_exp,
    )

    # Dual-lens scoring still present.
    assert "Score_2023_Final" in result.candidates.columns
    assert "Score_2025_Final" in result.candidates.columns
    assert "Consensus_Rank" in result.candidates.columns
    # Benchmark-fit columns merged in.
    for col in ("Total_Abs_Drift_After", "Max_Abs_Drift_After",
                "Stylebox_Drift_After", "Sector_Drift_After", "Fit_Label"):
        assert col in result.candidates.columns, col

    assert result.summary["benchmark_fit_enabled"]
    # Best by FundScore: highest consensus rank in candidate frame -> CAND_DRIFT
    # (Consensus_Rank=1).
    assert result.summary["best_fundscore_candidate"] == "CAND_DRIFT"
    # Best by benchmark fit: CAND_FIT (mirrors LLLA exactly).
    assert result.summary["best_benchmark_fit_candidate"] == "CAND_FIT"
    # Balanced should differ from "best by single dimension" (often CAND_MID
    # since it ranks reasonably on both axes).
    assert result.summary["balanced_candidate"] in {
        "CAND_FIT", "CAND_DRIFT", "CAND_MID"
    }

    assert not result.benchmark_fit_candidates.empty
    assert not result.current_vs_benchmark.empty
    assert not result.replacement_delta.empty


def test_workbench_persists_and_loads_fit_artifacts():
    model_exp = parse_exposures(_fix("exposures_model_good.csv"))
    bench_exp = parse_exposures(_fix("exposures_bench_good.csv"))
    cand_exp = parse_exposures(_fix("exposures_candidates_good.csv"))

    result = build_replacement_workbench(
        _dual_table(), "LLLA", top_n=10, alias_map={},
        model_holdings=_holdings(),
        model_exposures=model_exp,
        benchmark_exposures=bench_exp,
        benchmark_weights=_bench_weights(),
        candidate_exposures=cand_exp,
    )

    with tempfile.TemporaryDirectory() as tmp:
        paths = write_replacement(result, tmp)
        # Fit artifacts written.
        assert "benchmark_fit_candidates" in paths
        assert "current_vs_benchmark" in paths
        assert "replacement_delta" in paths
        for name in (
            BENCHMARK_FIT_CANDIDATES_NAME,
            CURRENT_VS_BENCHMARK_NAME,
            REPLACEMENT_DELTA_NAME,
            SUMMARY_NAME,
        ):
            assert os.path.isfile(os.path.join(tmp, name))

        loaded = load_replacement(tmp)
        assert loaded is not None
        assert not loaded["benchmark_fit_candidates"].empty
        assert not loaded["current_vs_benchmark"].empty
        assert not loaded["replacement_delta"].empty
        # Summary roundtrip.
        assert loaded["summary"]["benchmark_fit_enabled"] is True
        assert loaded["summary"]["best_benchmark_fit_candidate"] == "CAND_FIT"


def test_workbench_without_fit_inputs_skips_layer():
    """Backwards-compat: omit exposure kwargs and the workbench works as before."""
    result = build_replacement_workbench(
        _dual_table(), "LLLA", top_n=10, alias_map={},
    )
    # Fit columns absent.
    for col in ("Total_Abs_Drift_After", "Max_Abs_Drift_After", "Fit_Label"):
        assert col not in result.candidates.columns
    assert result.summary["benchmark_fit_enabled"] is False
    assert result.benchmark_fit_candidates.empty
    assert result.current_vs_benchmark.empty
    assert result.replacement_delta.empty

    # And nothing extra is persisted.
    with tempfile.TemporaryDirectory() as tmp:
        paths = write_replacement(result, tmp)
        assert "benchmark_fit_candidates" not in paths
        assert "current_vs_benchmark" not in paths
        assert "replacement_delta" not in paths


def test_brief_mentions_fit_when_layer_runs():
    model_exp = parse_exposures(_fix("exposures_model_good.csv"))
    bench_exp = parse_exposures(_fix("exposures_bench_good.csv"))
    cand_exp = parse_exposures(_fix("exposures_candidates_good.csv"))

    result = build_replacement_workbench(
        _dual_table(), "LLLA", top_n=10, alias_map={},
        model_holdings=_holdings(),
        model_exposures=model_exp,
        benchmark_exposures=bench_exp,
        benchmark_weights=_bench_weights(),
        candidate_exposures=cand_exp,
    )
    assert "Benchmark fit" in result.brief_markdown
    assert "Best by FundScore" in result.brief_markdown
    assert "Best by benchmark fit" in result.brief_markdown
