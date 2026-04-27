"""Tests for candidate_list_intake — parsing the simple committee
candidate-list CSV that drives the authoritative replacement universe.
"""

from __future__ import annotations

import io
import os
import sys

import pandas as pd
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_STREAMLIT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _STREAMLIT_DIR not in sys.path:
    sys.path.insert(0, _STREAMLIT_DIR)

from candidate_list_intake import (  # noqa: E402
    SYMBOL_HEADER_ALIASES,
    candidate_list_template_csv,
    candidate_symbol_name_map,
    parse_candidate_list,
    summarize_report,
    validate_candidate_list,
)


def _csv_buffer(text: str) -> io.StringIO:
    return io.StringIO(text)


# ---------------------------------------------------------------------------
# Schema flexibility — symbol header aliases
# ---------------------------------------------------------------------------

def test_parse_accepts_symbol_header():
    df = parse_candidate_list(_csv_buffer("Symbol,Name\nagi,Alpha\n"))
    assert list(df["Symbol"]) == ["AGI"]
    assert list(df["Name"]) == ["Alpha"]


def test_parse_accepts_ticker_header():
    df = parse_candidate_list(_csv_buffer("Ticker,Name\nbbb,Beta\n"))
    assert list(df["Symbol"]) == ["BBB"]


def test_parse_accepts_fund_symbol_header_case_insensitive():
    df = parse_candidate_list(_csv_buffer("FUND symbol,Name\nccc,Gamma\n"))
    assert list(df["Symbol"]) == ["CCC"]


def test_parse_accepts_candidate_symbol_header_with_underscore():
    df = parse_candidate_list(
        _csv_buffer("Candidate_Symbol,Name\nddd,Delta\n")
    )
    assert list(df["Symbol"]) == ["DDD"]


def test_parse_raises_when_no_symbol_column():
    with pytest.raises(ValueError):
        parse_candidate_list(_csv_buffer("Foo,Bar\n1,2\n"))


# ---------------------------------------------------------------------------
# Symbol normalization + dedup
# ---------------------------------------------------------------------------

def test_parse_strips_uppercases_and_drops_blanks():
    csv = "Symbol\n  prblx \n\n,\nspym\n"
    df = parse_candidate_list(_csv_buffer(csv))
    # Empty rows are dropped, whitespace stripped, upper-cased.
    assert list(df["Symbol"]) == ["PRBLX", "SPYM"]


def test_parse_drops_duplicate_symbols_keeping_first():
    csv = "Symbol,Name\nAAA,First\nAAA,Second\nBBB,Other\n"
    df = parse_candidate_list(_csv_buffer(csv))
    assert list(df["Symbol"]) == ["AAA", "BBB"]
    # First occurrence wins for the Name column.
    assert df.loc[df["Symbol"] == "AAA", "Name"].iloc[0] == "First"


# ---------------------------------------------------------------------------
# Optional metadata pass-through
# ---------------------------------------------------------------------------

def test_parse_preserves_optional_columns_and_renames_canonical():
    csv = (
        "Ticker,Fund Name,Active/Passive,Fund Type,Notes,Custom_Note\n"
        "AGI,Alpha Fund,Active,Mutual Fund,note1,custom1\n"
    )
    df = parse_candidate_list(_csv_buffer(csv))
    # Canonical renames + originals preserved.
    assert "Symbol" in df.columns
    assert "Active_Passive" in df.columns
    assert "Fund_Type" in df.columns
    assert "Notes" in df.columns
    # Unknown columns survive.
    assert "Custom_Note" in df.columns
    assert df.iloc[0]["Active_Passive"] == "Active"
    assert df.iloc[0]["Fund_Type"] == "Mutual Fund"


def test_parse_preserves_rationale_and_category():
    csv = "Symbol,Rationale,Category\nAAA,replace prblx,Large Blend\n"
    df = parse_candidate_list(_csv_buffer(csv))
    assert df.iloc[0]["Rationale"] == "replace prblx"
    assert df.iloc[0]["Category"] == "Large Blend"


def test_parse_accepts_dataframe_input():
    src = pd.DataFrame({"Ticker": ["aaa"], "Notes": ["x"]})
    df = parse_candidate_list(src)
    assert list(df["Symbol"]) == ["AAA"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_validate_flags_empty_input():
    rep = validate_candidate_list(pd.DataFrame())
    assert rep["failed"] is True
    assert any(e["code"] == "empty_input" for e in rep["errors"])


def test_validate_passes_for_simple_list():
    df = parse_candidate_list(_csv_buffer("Symbol\nAAA\nBBB\n"))
    rep = validate_candidate_list(df, source_label="committee_list")
    assert rep["failed"] is False
    assert rep["row_count"] == 2
    # info entries should mention row count.
    assert any(i["code"] == "row_count" for i in rep["info"])


def test_validate_warns_on_duplicates_after_parse():
    # parse_candidate_list dedupes, so we hand validate a frame that still
    # has duplicates to exercise the duplicate-warning path.
    df = pd.DataFrame({"Symbol": ["AAA", "AAA", "BBB"]})
    rep = validate_candidate_list(df)
    codes = [w["code"] for w in rep["warnings"]]
    assert "duplicate_symbol" in codes


def test_summarize_report_round_trip():
    df = parse_candidate_list(_csv_buffer("Symbol\nAAA\n"))
    rep = validate_candidate_list(df, source_label="committee_list")
    text = summarize_report(rep)
    assert text.startswith("[OK]")
    assert "committee_list" in text
    assert "1 candidate" in text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_template_csv_includes_required_symbol_column():
    text = candidate_list_template_csv()
    header = text.splitlines()[0]
    assert "Symbol" in header.split(",")
    # Template should be parseable round-trip.
    df = parse_candidate_list(_csv_buffer(text))
    assert not df.empty


def test_candidate_symbol_name_map_returns_uppercase_keys():
    df = parse_candidate_list(_csv_buffer("Ticker,Name\nagi,Alpha\nbbb,\n"))
    out = candidate_symbol_name_map(df)
    assert out == {"AGI": "Alpha"}


def test_symbol_header_aliases_cover_the_documented_set():
    # Hard-pin the recognised header set so a future refactor can't quietly
    # drop one of the four documented forms.
    keys = set(SYMBOL_HEADER_ALIASES.keys())
    assert {"symbol", "ticker", "fund symbol", "candidate symbol"}.issubset(keys)
