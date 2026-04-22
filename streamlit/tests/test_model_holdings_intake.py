"""Tests for model_holdings_intake."""

from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_STREAMLIT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
_FIXTURES = os.path.join(_HERE, "fixtures")
if _STREAMLIT_DIR not in sys.path:
    sys.path.insert(0, _STREAMLIT_DIR)

from model_holdings_intake import (  # noqa: E402
    _coerce_weight,
    normalize_weights,
    summarize,
    validate_model_holdings_dataframe,
    validate_model_holdings_file,
)


def _codes(report):
    return {f["code"] for f in report.get("findings", [])}


def test_good_holdings_passes():
    path = os.path.join(_FIXTURES, "model_holdings_good.csv")
    report = validate_model_holdings_file(path)
    assert report["failed"] is False
    assert report["row_count"] == 5
    assert report["model_names"] == ["Aggressive", "Moderate"]
    # Per-model weight sums should be ~1.0
    sums = report["weight_sums_by_model"]
    assert abs(sums["Moderate"] - 1.0) < 0.001
    assert abs(sums["Aggressive"] - 1.0) < 0.001


def test_coverage_against_universe_is_flagged():
    path = os.path.join(_FIXTURES, "model_holdings_good.csv")
    # Universe lacks CCC — Moderate sleeve's CCC is a missing symbol.
    report = validate_model_holdings_file(
        path, dual_score_symbols=["AAA", "BBB", "ZZZ"],
    )
    coverage = report["coverage"]
    assert coverage["available"] is True
    assert coverage["total_rows"] == 5
    assert coverage["covered_rows"] == 4  # 2 AAA + 2 BBB
    assert coverage["missing_rows"] == 1
    # Coverage = 4/5 = 0.80, which equals the default threshold 0.80.
    # The finding only fires BELOW threshold, so at exactly 0.80 it shouldn't.
    assert "low_universe_coverage" not in _codes(report)


def test_low_coverage_warns():
    path = os.path.join(_FIXTURES, "model_holdings_good.csv")
    report = validate_model_holdings_file(
        path, dual_score_symbols=["AAA"],
    )
    assert "low_universe_coverage" in _codes(report)


def test_bad_holdings_fails_with_multiple_errors():
    path = os.path.join(_FIXTURES, "model_holdings_bad.csv")
    report = validate_model_holdings_file(path)
    assert report["failed"] is True
    codes = _codes(report)
    # Duplicate AAA in Moderate, unparseable BBB weight, blank Symbol.
    assert "duplicate_model_symbol" in codes
    assert "unparseable_weight" in codes
    assert "blank_symbols" in codes


def test_missing_required_columns_errors():
    df = pd.DataFrame({"Symbol": ["AAA"], "Target_Weight": [0.5]})
    report = validate_model_holdings_dataframe(df)
    assert report["failed"] is True
    assert "missing_required_columns" in _codes(report)


def test_weight_sum_tolerance_warns():
    df = pd.DataFrame({
        "Model_Name": ["Moderate"] * 3,
        "Symbol": ["AAA", "BBB", "CCC"],
        "Target_Weight": ["40%", "40%", "40%"],  # 120% total — off
    })
    report = validate_model_holdings_dataframe(df)
    codes = _codes(report)
    assert "weight_sum_off" in codes
    # Not a hard failure.
    assert report["failed"] is False


@pytest.mark.parametrize("value,expected", [
    ("25%", 0.25),
    ("25", 25.0),
    ("0.25", 0.25),
    ("  50 % ", 0.50),
    ("", None),
    (None, None),
    ("junk", None),
    (0.33, 0.33),
])
def test_coerce_weight_handles_formats(value, expected):
    got = _coerce_weight(value)
    if expected is None:
        assert got is None
    else:
        assert got == pytest.approx(expected)


def test_normalize_weights_handles_percent_scale():
    df = pd.DataFrame({
        "Model_Name": ["M"] * 3,
        "Symbol": ["A", "B", "C"],
        "Target_Weight": ["40", "35", "25"],  # percent-ish, >1.5 max
    })
    out = normalize_weights(df)
    assert out["Target_Weight"].sum() == pytest.approx(1.0, abs=0.001)
    assert out["Target_Weight_Pct"].sum() == pytest.approx(100.0, abs=0.1)


def test_summarize_runs():
    path = os.path.join(_FIXTURES, "model_holdings_good.csv")
    report = validate_model_holdings_file(path)
    text = summarize(report)
    assert "Model Holdings Intake" in text
    assert "PASS" in text


# ---------------------------------------------------------------------------
# Alias behaviour
# ---------------------------------------------------------------------------

SANITIZED_ALIAS_MAP = {"ALIASA": "SCOREA", "ALIASB": "SCOREB"}


def _alias_holdings_df():
    return pd.DataFrame({
        "Model_Name": ["M"] * 4,
        "Symbol": ["ALIASA", "ALIASB", "KEEP", "GHOST"],
        "Target_Weight": ["25%", "25%", "25%", "25%"],
    })


def test_coverage_applies_aliases_before_missing_check():
    df = _alias_holdings_df()
    universe = ["KEEP", "SCOREA", "SCOREB"]  # ALIASA/ALIASB only reachable via alias
    report = validate_model_holdings_dataframe(
        df, dual_score_symbols=universe, alias_map=SANITIZED_ALIAS_MAP,
    )
    cov = report["coverage"]
    assert cov["available"] is True
    # 3 of 4 rows resolve: ALIASA->SCOREA, ALIASB->SCOREB, KEEP kept. GHOST misses.
    assert cov["covered_rows"] == 3
    assert cov["alias_applied_rows"] == 2
    assert cov["alias_covered_rows"] == 2
    assert cov["distinct_aliases_used"] == 2
    originals = {p["original"] for p in cov["alias_pairs"]}
    assert originals == {"ALIASA", "ALIASB"}
    # Still-missing originals surface unchanged.
    assert cov["sample_missing_symbols"] == ["GHOST"]


def test_alias_finding_emitted_when_alias_applied():
    df = _alias_holdings_df()
    universe = ["KEEP", "SCOREA", "SCOREB", "GHOST"]
    report = validate_model_holdings_dataframe(
        df, dual_score_symbols=universe, alias_map=SANITIZED_ALIAS_MAP,
    )
    assert "aliases_applied" in _codes(report)


def test_default_alias_map_loaded_when_none_passed():
    # Sanity: PRBLX + GSTKX resolve even without an explicit alias_map arg.
    df = pd.DataFrame({
        "Model_Name": ["M"] * 2,
        "Symbol": ["PRBLX", "GSTKX"],
        "Target_Weight": ["50%", "50%"],
    })
    universe = ["PRILX", "GSIKX"]
    report = validate_model_holdings_dataframe(
        df, dual_score_symbols=universe,
    )
    cov = report["coverage"]
    assert cov["covered_rows"] == 2
    assert cov["alias_applied_rows"] == 2
