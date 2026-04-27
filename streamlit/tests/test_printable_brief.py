"""Tests for printable_brief — the self-contained HTML replacement brief.

These tests intentionally drive both the in-memory ``ReplacementResult``
path and the persisted ``load_replacement`` dict path, since the Streamlit
page renders both depending on whether a build just happened or the user
revisited an earlier run.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import zipfile

import pandas as pd
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_STREAMLIT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _STREAMLIT_DIR not in sys.path:
    sys.path.insert(0, _STREAMLIT_DIR)

from printable_brief import (  # noqa: E402
    EPHEMERAL_STORAGE_NOTE,
    build_artifact_zip,
    render_printable_brief_html,
)
from replacement_workbench import (  # noqa: E402
    ReplacementResult,
    build_replacement_workbench,
    load_replacement,
    write_replacement,
)


# Reuse the same dual-table shape as test_replacement_workbench so the
# fixtures stay in sync with the production columns.
def _dual_table() -> pd.DataFrame:
    return pd.DataFrame([
        {"Symbol": "PRBLX", "Name": "Parnassus Core Equity",
         "Category": "Large Blend", "Fund_Type": "Active",
         "Score_2023_Final": 60.0, "Score_2025_Final": 45.0,
         "Score_Band_2023": "REVIEW", "Score_Band_2025": "WEAK",
         "Quadrant": "Q3_Only_2023", "Consensus_Rank": 7,
         "Score_Gap": -15.0, "Rank_2023": 4, "Rank_2025": 9,
         "Action_Flag": "DROP", "Primary_Driver": "fees",
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0},
        {"Symbol": "BBB", "Name": "Beta Index",
         "Category": "Large Blend", "Fund_Type": "Passive",
         "Score_2023_Final": 92.0, "Score_2025_Final": 90.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
         "Quadrant": "Q1_Both_Strong", "Consensus_Rank": 1,
         "Score_Gap": -2.0, "Rank_2023": 1, "Rank_2025": 2,
         "Action_Flag": "LEAD", "Primary_Driver": "track",
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0},
        {"Symbol": "CCC", "Name": "Gamma Active",
         "Category": "Large Blend", "Fund_Type": "Active",
         "Score_2023_Final": 85.0, "Score_2025_Final": 70.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "REVIEW",
         "Quadrant": "Q3_Only_2023", "Consensus_Rank": 3,
         "Score_Gap": -15.0, "Rank_2023": 2, "Rank_2025": 5,
         "Action_Flag": "REVIEW", "Primary_Driver": "alpha",
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0},
        {"Symbol": "DDD", "Name": "Delta Active",
         "Category": "Large Blend", "Fund_Type": "Active",
         "Score_2023_Final": 70.0, "Score_2025_Final": 88.0,
         "Score_Band_2023": "REVIEW", "Score_Band_2025": "STRONG",
         "Quadrant": "Q2_Only_2025", "Consensus_Rank": 2,
         "Score_Gap": 18.0, "Rank_2023": 5, "Rank_2025": 3,
         "Action_Flag": "LEAD", "Primary_Driver": "quality",
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0},
    ])


def _make_result_for_prblx(*, apply_fund_type_filter=False) -> ReplacementResult:
    # Default to disabling the inferred fund-type filter so the cross-type
    # legacy assertions (passive BBB ranked alongside active CCC/DDD) keep
    # holding. Tests that want to exercise the new default opt back in.
    return build_replacement_workbench(
        _dual_table(),
        "PRBLX",
        top_n=10,
        alias_map={},
        run_date="2026-04-30",
        apply_fund_type_filter=apply_fund_type_filter,
    )


# ---------------------------------------------------------------------------
# Core rendering — structure, content, and escaping
# ---------------------------------------------------------------------------

def test_render_returns_self_contained_html_document():
    result = _make_result_for_prblx()
    out = render_printable_brief_html(result)
    assert out.startswith("<!DOCTYPE html>")
    assert "</html>" in out
    # Self-contained: CSS embedded, no external <link> stylesheets.
    assert "<style>" in out
    assert "<link" not in out
    # The print stylesheet is embedded so browser Print → PDF works.
    assert "@media print" in out


def test_brief_includes_current_holding_summary():
    result = _make_result_for_prblx()
    out = render_printable_brief_html(result)
    # Committee ticker + resolved scoring symbol + name + category + scores.
    assert "PRBLX" in out
    assert "Parnassus Core Equity" in out
    assert "Large Blend" in out
    # Both 2023 and 2025 scores surface — the dual-lens contract.
    assert "60.0" in out
    assert "45.0" in out
    # Bands appear (non-blended).
    assert "REVIEW" in out
    assert "WEAK" in out


def test_brief_includes_methodology_and_top_candidates_table():
    result = _make_result_for_prblx()
    out = render_printable_brief_html(result)
    assert "Methodology" in out
    assert "Top candidates by FundScore" in out
    # Top-3 candidates by Consensus_Rank should appear in order.
    bbb_idx = out.index("BBB")
    ddd_idx = out.index("DDD")
    ccc_idx = out.index("CCC")
    assert bbb_idx < ddd_idx < ccc_idx
    # Column headers we promised the user.
    for label in ("Symbol", "Name", "Type", "2023", "2025", "Reason / Fit"):
        assert label in out


def test_brief_includes_data_quality_and_ephemeral_storage_note():
    result = _make_result_for_prblx()
    out = render_printable_brief_html(result)
    assert "Data quality" in out
    # The exact ephemeral-storage caveat must appear so a printed page
    # explains why the server path isn't authoritative.
    assert "ephemeral" in out
    assert EPHEMERAL_STORAGE_NOTE in out


def test_brief_renders_alias_resolution_when_applied():
    # Build an alias case that exercises the share-class resolver.
    dt = _dual_table()
    alias_map = {"ALIASA": "BBB"}
    result = build_replacement_workbench(
        dt, "ALIASA", alias_map=alias_map, top_n=10, run_date="2026-04-30",
    )
    assert result.alias_applied is True
    out = render_printable_brief_html(result)
    assert "ALIASA" in out
    assert "alias" in out.lower()


def test_html_escapes_potentially_unsafe_characters():
    # Inject < > & " into a name to confirm escaping holds at the HTML edge.
    dt = _dual_table()
    dt.loc[dt["Symbol"] == "BBB", "Name"] = '<script>alert("x")</script> & co'
    result = build_replacement_workbench(
        dt, "PRBLX", top_n=10, alias_map={}, run_date="2026-04-30",
        apply_fund_type_filter=False,
    )
    out = render_printable_brief_html(result)
    assert "<script>alert" not in out
    assert "&lt;script&gt;" in out
    assert "&amp;" in out


def test_render_accepts_loaded_artifact_dict_round_trip():
    # The Streamlit page renders from load_replacement when revisiting an
    # archived run — exercise that path explicitly.
    result = _make_result_for_prblx()
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = os.path.join(tmp, "PRBLX")
        write_replacement(result, out_dir)
        loaded = load_replacement(out_dir)
    assert loaded is not None
    out = render_printable_brief_html(loaded, run_date="2026-04-30")
    assert "PRBLX" in out
    assert "Top candidates by FundScore" in out
    # Run date provided by the caller should appear in the header.
    assert "2026-04-30" in out


def test_render_handles_empty_candidate_list_gracefully():
    # Unknown ticker → empty candidates; brief must still render and tell
    # the user nothing was found rather than crashing.
    result = build_replacement_workbench(
        _dual_table(), "UNKNOWN", top_n=10, alias_map={},
    )
    assert result.candidates.empty
    out = render_printable_brief_html(result)
    assert "Replacement Brief" in out
    assert "No same-category candidates" in out


def test_render_rejects_unknown_input_type():
    with pytest.raises(TypeError):
        render_printable_brief_html(42)


# ---------------------------------------------------------------------------
# ZIP bundle
# ---------------------------------------------------------------------------

def test_build_artifact_zip_contains_csvs_and_briefs():
    result = _make_result_for_prblx()
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = os.path.join(tmp, "PRBLX")
        write_replacement(result, out_dir)
        loaded = load_replacement(out_dir)
    html_brief = render_printable_brief_html(loaded)
    blob = build_artifact_zip(loaded, html_brief=html_brief)

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = set(zf.namelist())
        assert "PRBLX_printable_brief.html" in names
        assert "PRBLX_replacement_brief.md" in names
        assert "PRBLX_replacement_summary.json" in names
        assert "PRBLX_replacement_candidates.csv" in names
        # Empty frames stay out — no bench-fit artifacts in this fixture.
        assert "PRBLX_benchmark_fit_candidates.csv" not in names
        # The HTML payload round-trips intact.
        with zf.open("PRBLX_printable_brief.html") as f:
            assert b"<!DOCTYPE html>" in f.read()


def test_build_artifact_zip_skips_empty_frames():
    # Build a result whose persisted form has no candidates.
    result = build_replacement_workbench(
        _dual_table(), "UNKNOWN", top_n=10, alias_map={},
    )
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = os.path.join(tmp, "UNKNOWN")
        write_replacement(result, out_dir)
        loaded = load_replacement(out_dir)
    blob = build_artifact_zip(loaded, html_brief="<html></html>")
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = set(zf.namelist())
    # Summary JSON is always written; CSVs are gated on non-empty frames.
    assert "UNKNOWN_replacement_summary.json" in names
    assert "UNKNOWN_replacement_candidates.csv" not in names
