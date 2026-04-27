"""Tests for exposure_intake (YCharts wide-format exposure parser)."""

from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_STREAMLIT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _STREAMLIT_DIR not in sys.path:
    sys.path.insert(0, _STREAMLIT_DIR)

from exposure_intake import (  # noqa: E402
    CLEAN_COLUMNS,
    SECTOR_BUCKETS,
    STYLEBOX_BUCKETS,
    parse_exposures,
    summarize_report,
    validate_exposures,
)


FIX_DIR = os.path.join(_HERE, "fixtures")


def _fix(name: str) -> str:
    return os.path.join(FIX_DIR, name)


def test_parse_good_file_normalizes_columns():
    df = parse_exposures(_fix("exposures_model_good.csv"))
    assert list(df.columns) == CLEAN_COLUMNS
    assert len(df) == 5
    # Symbols upper-cased.
    assert df["Symbol"].iloc[0] == "LLLA"
    # Numeric coercion.
    for col in STYLEBOX_BUCKETS + SECTOR_BUCKETS:
        assert pd.api.types.is_numeric_dtype(df[col]), col


def test_validate_good_file_no_errors():
    df = parse_exposures(_fix("exposures_model_good.csv"))
    rep = validate_exposures(df, source_label="model_good")
    assert not rep["failed"], rep
    assert rep["row_count"] == 5
    # No warnings expected — all rows sum to 1.0.
    sb_warnings = [w for w in rep["warnings"]
                   if w["code"] in ("stylebox_sum_off", "sector_sum_off")]
    assert sb_warnings == []


def test_validate_bad_file_flags_dups_and_blank_and_low_sum():
    df = parse_exposures(_fix("exposures_bad_sums.csv"))
    rep = validate_exposures(df, source_label="bad")

    error_codes = [e["code"] for e in rep["errors"]]
    assert "missing_symbol" in error_codes  # blank Symbol row
    assert rep["failed"]

    warning_codes = [w["code"] for w in rep["warnings"]]
    assert "duplicate_symbol" in warning_codes
    assert "stylebox_sum_off" in warning_codes
    assert "sector_sum_off" not in warning_codes  # sectors still sum to 1


def test_validate_empty_input_fails():
    rep = validate_exposures(pd.DataFrame(), source_label="empty")
    assert rep["failed"]
    assert any(e["code"] == "empty_input" for e in rep["errors"])


def test_validate_missing_columns_fails():
    df = pd.DataFrame({"Symbol": ["AAA"], "Name": ["A"]})
    rep = validate_exposures(df, source_label="missing")
    # parse_exposures isn't called here — validate_exposures should still flag.
    assert rep["failed"]
    assert any(e["code"] == "missing_columns" for e in rep["errors"])


def test_summarize_report_includes_status_and_codes():
    df = parse_exposures(_fix("exposures_bad_sums.csv"))
    rep = validate_exposures(df, source_label="bad")
    text = summarize_report(rep)
    assert "FAILED" in text
    assert "duplicate_symbol" in text
    assert "stylebox_sum_off" in text


def test_parse_accepts_dataframe_input():
    df_in = pd.read_csv(_fix("exposures_model_good.csv"))
    df_out = parse_exposures(df_in)
    assert list(df_out.columns) == CLEAN_COLUMNS
    assert len(df_out) == len(df_in)
