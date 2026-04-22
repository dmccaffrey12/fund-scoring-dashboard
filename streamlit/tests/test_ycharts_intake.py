"""
Tests for the ycharts_intake validator.

Covers:
  - clean 2025 / 2023 exports pass
  - missing required column is an error and sets `failed`
  - duplicate / blank symbols surface as expected findings
  - unparseable numeric + Index Fund values
  - pair joinability reporting (full overlap + partial overlap)
  - run_archive preflight integration hook
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pandas as pd
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_STREAMLIT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
_FIXTURES = os.path.join(_HERE, "fixtures")
if _STREAMLIT_DIR not in sys.path:
    sys.path.insert(0, _STREAMLIT_DIR)

from ycharts_intake import (  # noqa: E402
    DEFAULT_NULL_RATE_WARN,
    _cli,
    preflight_for_archive,
    summarize,
    validate_dataframe,
    validate_file,
    validate_pair,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _findings_by_code(report):
    return {f["code"] for f in report.get("findings", [])}


# ---------------------------------------------------------------------------
# Single-file: happy path
# ---------------------------------------------------------------------------

def test_validate_2025_good_passes():
    path = os.path.join(_FIXTURES, "ycharts_2025_good.csv")
    report = validate_file(path, "2025")
    assert report["failed"] is False
    assert report["schema"] == "2025"
    assert report["row_count"] == 3
    assert report["column_count"] == 29
    assert report["missing_required_columns"] == []
    assert report["symbol_stats"]["blank_symbol_count"] == 0
    assert report["symbol_stats"]["duplicate_symbol_count"] == 0
    assert report["index_fund_stats"]["passive_count"] == 1
    assert report["index_fund_stats"]["active_count"] == 2
    assert report["index_fund_stats"]["unparseable_count"] == 0


def test_validate_2023_good_passes():
    path = os.path.join(_FIXTURES, "ycharts_2023_good.csv")
    report = validate_file(path, "2023")
    assert report["failed"] is False
    assert report["row_count"] == 3
    # 2023 schema has no Index Fund column.
    assert report["index_fund_stats"] is None


# ---------------------------------------------------------------------------
# Single-file: failure modes
# ---------------------------------------------------------------------------

def test_missing_required_column_is_error():
    path = os.path.join(_FIXTURES, "ycharts_2023_missing_col.csv")
    report = validate_file(path, "2023")
    assert report["failed"] is True
    assert "Annual Report Expense Ratio" in report["missing_required_columns"]
    assert "missing_required_columns" in _findings_by_code(report)


def test_bad_2025_surfaces_symbol_numeric_and_index_fund_issues():
    path = os.path.join(_FIXTURES, "ycharts_2025_bad.csv")
    report = validate_file(path, "2025")
    codes = _findings_by_code(report)
    # Errors
    assert "blank_symbols" in codes
    assert "unparseable_numeric" in codes  # Net Expense Ratio = "not-a-number"
    assert "unparseable_index_fund" in codes  # "maybe"
    # Warnings
    assert "duplicate_symbols" in codes
    # Must be marked failed because the critical numeric + symbol errors exist.
    assert report["failed"] is True


def test_missing_file_returns_failed_report():
    report = validate_file("/nonexistent/path/to/file.csv", "2025")
    assert report["failed"] is True
    assert "file_not_found" in _findings_by_code(report)


# ---------------------------------------------------------------------------
# DataFrame-level API
# ---------------------------------------------------------------------------

def test_validate_dataframe_unknown_schema_raises():
    with pytest.raises(ValueError):
        validate_dataframe(pd.DataFrame(), schema="1999")


def test_null_rate_threshold_triggers_warning():
    path = os.path.join(_FIXTURES, "ycharts_2025_good.csv")
    df = pd.read_csv(path, dtype=str)
    # Blank out Net Expense Ratio entirely — 100% null.
    df["Net Expense Ratio"] = ""
    report = validate_dataframe(df, "2025", null_rate_threshold=0.5)
    assert "high_null_rate" in _findings_by_code(report)
    # High null rate is only a warning, so this should not fail.
    assert report["failed"] is False


# ---------------------------------------------------------------------------
# Pair / joinability
# ---------------------------------------------------------------------------

def test_validate_pair_full_overlap_passes():
    pair = validate_pair(
        path_2025=os.path.join(_FIXTURES, "ycharts_2025_good.csv"),
        path_2023=os.path.join(_FIXTURES, "ycharts_2023_good.csv"),
    )
    assert pair["failed"] is False
    join = pair["join"]
    assert join["available"] is True
    assert join["symbols_common"] == 3
    assert join["symbols_only_2025"] == 0
    assert join["symbols_only_2023"] == 0
    assert join["overlap_rate_vs_smaller"] == 1.0


def test_validate_pair_partial_overlap_warns():
    pair = validate_pair(
        path_2025=os.path.join(_FIXTURES, "ycharts_2025_join_partial.csv"),
        path_2023=os.path.join(_FIXTURES, "ycharts_2023_good.csv"),
        min_overlap_rate=0.80,
    )
    # Only "AAA" is shared (1 of 3 → 33%).
    join = pair["join"]
    assert join["symbols_common"] == 1
    assert join["overlap_rate_vs_smaller"] == pytest.approx(0.3333, abs=1e-3)
    codes = {f["code"] for f in pair["join_findings"]}
    assert "low_symbol_overlap" in codes


def test_validate_pair_single_file_only():
    pair = validate_pair(
        path_2025=os.path.join(_FIXTURES, "ycharts_2025_good.csv"),
    )
    assert pair["report_2025"] is not None
    assert pair["report_2023"] is None
    assert pair["join"] == {"available": False}


# ---------------------------------------------------------------------------
# Summary rendering
# ---------------------------------------------------------------------------

def test_summarize_contains_status_line():
    path = os.path.join(_FIXTURES, "ycharts_2025_good.csv")
    report = validate_file(path, "2025")
    text = summarize(report)
    assert "PASS" in text
    assert "2025" in text
    assert "Row count: 3" in text


def test_summarize_pair_contains_joinability_section():
    pair = validate_pair(
        path_2025=os.path.join(_FIXTURES, "ycharts_2025_good.csv"),
        path_2023=os.path.join(_FIXTURES, "ycharts_2023_good.csv"),
    )
    text = summarize(pair)
    assert "Joinability" in text
    assert "PAIR STATUS" in text


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_writes_json_and_returns_zero_on_pass(tmp_path, capsys):
    out_path = tmp_path / "report.json"
    rc = _cli([
        "--path-2025", os.path.join(_FIXTURES, "ycharts_2025_good.csv"),
        "--path-2023", os.path.join(_FIXTURES, "ycharts_2023_good.csv"),
        "--json-out", str(out_path),
        "--quiet",
    ])
    assert rc == 0
    assert out_path.exists()
    payload = json.loads(out_path.read_text())
    assert payload["failed"] is False


def test_cli_returns_nonzero_on_failure():
    rc = _cli([
        "--path-2023", os.path.join(_FIXTURES, "ycharts_2023_missing_col.csv"),
        "--quiet",
    ])
    assert rc == 1


# ---------------------------------------------------------------------------
# Run-archive integration hook
# ---------------------------------------------------------------------------

def test_preflight_for_archive_raises_on_failure():
    with pytest.raises(ValueError):
        preflight_for_archive(
            path_2025=os.path.join(_FIXTURES, "ycharts_2025_good.csv"),
            path_2023=os.path.join(_FIXTURES, "ycharts_2023_missing_col.csv"),
            strict=True,
        )


def test_run_archive_writes_intake_report_when_preflight_enabled(tmp_path):
    """create_run_archive(preflight="warn", ...) should drop an intake_report.json
    next to the usual validation_report.json and record preflight in metadata."""
    from run_archive import create_run_archive, load_run

    table = pd.DataFrame({
        "Symbol": ["AAA", "BBB"],
        "Score_2023_Final": [80.0, 60.0],
        "Score_2025_Final": [85.0, 55.0],
    })
    target = create_run_archive(
        run_date="2026-04-22",
        runs_dir=str(tmp_path),
        path_2025=os.path.join(_FIXTURES, "ycharts_2025_good.csv"),
        path_2023=os.path.join(_FIXTURES, "ycharts_2023_good.csv"),
        table=table,  # table provided → preflight is skipped by design
        preflight="warn",
    )
    # When `table` is supplied, preflight is skipped — metadata should
    # record ran=False.
    run = load_run("2026-04-22", runs_dir=str(tmp_path))
    assert run["metadata"]["preflight"]["mode"] == "warn"
    assert run["metadata"]["preflight"]["ran"] is False


def test_preflight_for_archive_returns_report_when_not_strict():
    report = preflight_for_archive(
        path_2025=os.path.join(_FIXTURES, "ycharts_2025_good.csv"),
        path_2023=os.path.join(_FIXTURES, "ycharts_2023_missing_col.csv"),
        strict=False,
    )
    assert report["failed"] is True
    assert report["report_2023"]["failed"] is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
