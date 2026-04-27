"""Tests for benchmark_fit module."""

from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_STREAMLIT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _STREAMLIT_DIR not in sys.path:
    sys.path.insert(0, _STREAMLIT_DIR)

from benchmark_fit import (  # noqa: E402
    ALL_BUCKETS,
    DEFAULT_BENCHMARK_WEIGHTS,
    benchmark_exposure,
    benchmark_weights_from_mapping,
    build_benchmark_fit_artifacts,
    drift_metrics,
    fit_label,
    simulate_replacements,
    weighted_exposure,
)
from exposure_intake import SECTOR_BUCKETS, STYLEBOX_BUCKETS, parse_exposures  # noqa: E402


FIX_DIR = os.path.join(_HERE, "fixtures")


def _fix(name: str) -> str:
    return os.path.join(FIX_DIR, name)


def _make_holdings():
    # 100/0 sleeve: heavy LLLA (large blend), some mid/small/foreign/EM.
    return pd.DataFrame([
        {"Model_Name": "100/0", "Symbol": "LLLA", "Target_Weight": 0.50},
        {"Model_Name": "100/0", "Symbol": "LLLB", "Target_Weight": 0.10},
        {"Model_Name": "100/0", "Symbol": "LLLC", "Target_Weight": 0.10},
        {"Model_Name": "100/0", "Symbol": "LLLD", "Target_Weight": 0.20},
        {"Model_Name": "100/0", "Symbol": "LLLE", "Target_Weight": 0.10},
    ])


def _make_bench_weights():
    return {"LLLA": 0.58, "LLLD": 0.24, "LLLB": 0.06, "LLLC": 0.06, "LLLE": 0.06}


def test_default_benchmark_weights_sum_to_one():
    assert pytest.approx(sum(DEFAULT_BENCHMARK_WEIGHTS.values()), abs=1e-9) == 1.0


def test_weighted_exposure_matches_manual_weighting():
    exposures = parse_exposures(_fix("exposures_model_good.csv"))
    weights = {"LLLA": 0.5, "LLLB": 0.5}

    out = weighted_exposure(weights, exposures)
    # LargeBlend: 0.5*0.40 + 0.5*0.05 = 0.225
    assert pytest.approx(out["LargeBlend"], abs=1e-9) == 0.225
    # Technology: 0.5*0.30 + 0.5*0.20 = 0.25
    assert pytest.approx(out["Technology"], abs=1e-9) == 0.25
    assert out["_missing"] == []
    assert pytest.approx(out["_matched_weight"], abs=1e-9) == 1.0


def test_weighted_exposure_reports_missing_symbols():
    exposures = parse_exposures(_fix("exposures_model_good.csv"))
    out = weighted_exposure({"LLLA": 0.5, "ZZZ_NOT_THERE": 0.5}, exposures)
    assert out["_missing"] == ["ZZZ_NOT_THERE"]
    assert pytest.approx(out["_matched_weight"], abs=1e-9) == 0.5


def test_drift_metrics_active_weights_and_aggregates():
    actual = {b: 0.0 for b in ALL_BUCKETS}
    target = {b: 0.0 for b in ALL_BUCKETS}
    actual["LargeBlend"] = 0.40
    target["LargeBlend"] = 0.30
    actual["Technology"] = 0.30
    target["Technology"] = 0.25

    m = drift_metrics(actual, target)
    assert pytest.approx(m["active"]["LargeBlend"], abs=1e-9) == 0.10
    assert pytest.approx(m["active"]["Technology"], abs=1e-9) == 0.05
    assert pytest.approx(m["total_abs_drift"], abs=1e-9) == 0.15
    assert pytest.approx(m["max_abs_drift"], abs=1e-9) == 0.10
    assert m["max_drift_bucket"] == "LargeBlend"
    assert pytest.approx(m["stylebox_total_abs_drift"], abs=1e-9) == 0.10
    assert pytest.approx(m["sector_total_abs_drift"], abs=1e-9) == 0.05


def test_fit_label_thresholds():
    # Strong fit
    assert fit_label({"total_abs_drift": 0.05, "max_abs_drift": 0.02}) == "Strong Fit"
    # Acceptable
    assert fit_label({"total_abs_drift": 0.30, "max_abs_drift": 0.08}) == "Acceptable"
    # Drift Risk: max exceeds acceptable
    assert fit_label({"total_abs_drift": 0.30, "max_abs_drift": 0.20}) == "Drift Risk"
    # Drift Risk: total exceeds acceptable
    assert fit_label({"total_abs_drift": 0.50, "max_abs_drift": 0.05}) == "Drift Risk"


def test_simulate_replacements_ranks_better_fit_first():
    model_exp = parse_exposures(_fix("exposures_model_good.csv"))
    bench_exp = parse_exposures(_fix("exposures_bench_good.csv"))
    cand_exp = parse_exposures(_fix("exposures_candidates_good.csv"))
    holdings = _make_holdings()

    table = simulate_replacements(
        model_holdings=holdings,
        model_exposures=model_exp,
        candidate_exposures=cand_exp,
        benchmark_weights=_make_bench_weights(),
        benchmark_exposures=bench_exp,
        target_symbol="LLLA",
    )

    assert not table.empty
    # CAND_FIT mirrors LLLA exactly, so replacing LLLA with itself-shaped
    # candidate should yield the smallest after-drift.
    assert table.iloc[0]["Candidate_Symbol"] == "CAND_FIT"
    # CAND_DRIFT is heavily growth/tech-skewed — should rank worst of the 3.
    assert table.iloc[-1]["Candidate_Symbol"] == "CAND_DRIFT"
    # Sorted ascending by Total_Abs_Drift_After.
    afters = table["Total_Abs_Drift_After"].tolist()
    assert afters == sorted(afters)
    # Fit_Rank starts at 1.
    assert table["Fit_Rank"].iloc[0] == 1


def test_build_artifacts_emits_expected_frames_and_summary():
    model_exp = parse_exposures(_fix("exposures_model_good.csv"))
    bench_exp = parse_exposures(_fix("exposures_bench_good.csv"))
    cand_exp = parse_exposures(_fix("exposures_candidates_good.csv"))
    holdings = _make_holdings()

    out = build_benchmark_fit_artifacts(
        model_holdings=holdings,
        model_exposures=model_exp,
        benchmark_exposures=bench_exp,
        benchmark_weights=_make_bench_weights(),
        candidate_exposures=cand_exp,
        target_symbol="LLLA",
    )

    cb = out["current_vs_benchmark"]
    assert set(cb["Bucket_Type"].unique()) == {"Stylebox", "Sector"}
    assert len(cb) == len(STYLEBOX_BUCKETS) + len(SECTOR_BUCKETS)
    assert {"Model_Exposure", "Benchmark_Exposure", "Active_Weight"} <= set(cb.columns)

    assert out["baseline_fit_label"] in ("Strong Fit", "Acceptable", "Drift Risk")
    assert not out["replacement_table"].empty
    assert "Candidate_Symbol" in out["replacement_delta"].columns


def test_build_artifacts_runs_without_target_symbol():
    """Baseline-only mode: no target_symbol means no replacement table."""
    model_exp = parse_exposures(_fix("exposures_model_good.csv"))
    bench_exp = parse_exposures(_fix("exposures_bench_good.csv"))
    holdings = _make_holdings()

    out = build_benchmark_fit_artifacts(
        model_holdings=holdings,
        model_exposures=model_exp,
        benchmark_exposures=bench_exp,
        benchmark_weights=_make_bench_weights(),
    )
    assert out["replacement_table"].empty
    assert out["replacement_delta"].empty
    assert not out["current_vs_benchmark"].empty


def test_benchmark_weights_from_mapping_filters_invalid():
    out = benchmark_weights_from_mapping({
        "spym": 0.5, "EFA": "0.5", "  ": 0.1, "BAD": "x", "ZERO": 0.0,
    })
    assert out == {"SPYM": 0.5, "EFA": 0.5}
