"""Tests for symbol_aliases."""

from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_STREAMLIT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _STREAMLIT_DIR not in sys.path:
    sys.path.insert(0, _STREAMLIT_DIR)

from symbol_aliases import (  # noqa: E402
    DEFAULT_ALIASES,
    DEFAULT_ALIAS_CSV_PATH,
    apply_aliases,
    load_aliases_from_csv,
    load_default_aliases,
    resolve_symbol,
    summarize_alias_usage,
)


# Sanitized alias map used across these tests. Real-world defaults live in
# DEFAULT_ALIASES / the shipped config CSV; the checked-in fixtures below use
# made-up tickers so we never need raw user data in tests.
SANITIZED_ALIASES = {
    "ALIASA": "SCOREA",  # stand-in for a share-class alias pair
    "ALIASB": "SCOREB",
}


def test_default_aliases_include_known_share_class_pairs():
    # Baked-in defaults cover the four share-class pairs identified against
    # the 4/22 model library: Parnassus Core, GS Small Cap Growth Insights,
    # PIMCO Income, Fidelity Emerging Markets.
    for original, scoring in (
        ("PRBLX", "PRILX"),
        ("GSTKX", "GSIKX"),
        ("PONPX", "PIMIX"),
        ("FECMX", "FEMKX"),
    ):
        assert DEFAULT_ALIASES.get(original) == scoring


def test_shipped_config_csv_parses():
    # The config CSV shipped in the repo must parse cleanly.
    assert os.path.isfile(DEFAULT_ALIAS_CSV_PATH)
    loaded = load_aliases_from_csv(DEFAULT_ALIAS_CSV_PATH)
    for original in ("PRBLX", "GSTKX", "PONPX", "FECMX"):
        assert original in loaded


def test_load_default_aliases_merges_extra(tmp_path):
    extra = tmp_path / "extra.csv"
    extra.write_text(
        "Original_Symbol,Scoring_Symbol,Reason\n"
        "ALIASA,SCOREA,test alias\n"
    )
    merged = load_default_aliases(extra_path=str(extra))
    assert merged["ALIASA"] == "SCOREA"
    # baked-in defaults still present
    assert "PRBLX" in merged


def test_load_aliases_from_csv_missing_required_column_raises(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("Original_Symbol,Other\nALIASA,whatever\n")
    with pytest.raises(ValueError):
        load_aliases_from_csv(str(bad))


def test_load_aliases_from_csv_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_aliases_from_csv("/does/not/exist.csv")


def test_load_aliases_from_csv_skips_self_and_blank_rows(tmp_path):
    csv = tmp_path / "a.csv"
    csv.write_text(
        "Original_Symbol,Scoring_Symbol,Reason\n"
        "ALIASA,SCOREA,ok\n"
        ",SCOREB,blank original\n"
        "ALIASC,,blank target\n"
        "SAME,SAME,identity\n"
    )
    loaded = load_aliases_from_csv(str(csv))
    assert loaded == {"ALIASA": "SCOREA"}


def test_resolve_symbol_respects_universe():
    # When the original symbol is already in the universe the alias is ignored.
    aliases = {"ALIASA": "SCOREA"}
    assert resolve_symbol("ALIASA", aliases, universe={"ALIASA"}) == "ALIASA"
    assert resolve_symbol("ALIASA", aliases, universe={"SOMETHING"}) == "SCOREA"
    # No universe -> alias always applied.
    assert resolve_symbol("ALIASA", aliases) == "SCOREA"


def test_resolve_symbol_normalizes_case_and_whitespace():
    aliases = {"ALIASA": "SCOREA"}
    assert resolve_symbol(" aliasa ", aliases) == "SCOREA"


def test_apply_aliases_adds_expected_columns():
    holdings = pd.DataFrame({
        "Symbol": ["ALIASA", "KEEP", "aliasb"],
        "Target_Weight": [0.5, 0.3, 0.2],
    })
    out = apply_aliases(holdings, alias_map=SANITIZED_ALIASES, universe={"KEEP"})
    assert list(out["Original_Symbol"]) == ["ALIASA", "KEEP", "ALIASB"]
    assert list(out["Scoring_Symbol"]) == ["SCOREA", "KEEP", "SCOREB"]
    assert list(out["Alias_Applied"]) == [True, False, True]
    # Original columns preserved.
    assert list(out["Target_Weight"]) == [0.5, 0.3, 0.2]


def test_apply_aliases_universe_match_wins_over_alias():
    # Even if we alias ALIASA -> SCOREA, when ALIASA is present in the
    # universe we leave it alone so we don't clobber valid matches.
    holdings = pd.DataFrame({"Symbol": ["ALIASA"]})
    out = apply_aliases(
        holdings, alias_map={"ALIASA": "SCOREA"}, universe={"ALIASA", "SCOREA"},
    )
    assert out.iloc[0]["Scoring_Symbol"] == "ALIASA"
    assert out.iloc[0]["Alias_Applied"] is False or not out.iloc[0]["Alias_Applied"]


def test_summarize_alias_usage_reports_pairs_and_missing():
    holdings = pd.DataFrame({
        "Symbol": ["ALIASA", "KEEP", "ALIASB", "UNKNOWN"],
    })
    resolved = apply_aliases(
        holdings, alias_map=SANITIZED_ALIASES,
        universe={"KEEP", "SCOREA", "SCOREB"},
    )
    summary = summarize_alias_usage(
        resolved, universe={"KEEP", "SCOREA", "SCOREB"},
    )
    assert summary["total_rows"] == 4
    assert summary["alias_applied_rows"] == 2
    assert summary["distinct_aliases_used"] == 2
    originals = {p["original"] for p in summary["alias_pairs"]}
    assert originals == {"ALIASA", "ALIASB"}
    assert summary["still_unscored_symbols"] == ["UNKNOWN"]


def test_apply_aliases_without_symbol_column_is_noop():
    df = pd.DataFrame({"X": [1, 2]})
    out = apply_aliases(df, alias_map={"A": "B"})
    assert "Scoring_Symbol" not in out.columns
    # Original is unchanged
    assert list(out["X"]) == [1, 2]
