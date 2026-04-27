"""Tests for replacement_workbench."""

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

from replacement_workbench import (  # noqa: E402
    BRIEF_NAME,
    CANDIDATES_NAME,
    CURRENT_PROFILE_NAME,
    ReplacementResult,
    SUMMARY_NAME,
    WORKBENCH_SUBDIR,
    build_replacement_workbench,
    load_replacement,
    run_replacement_for_run,
    workbench_dir,
    write_replacement,
)


# ---------------------------------------------------------------------------
# Sanitized fixtures — deterministic dual-score substrate for the workbench.
# Tickers are made-up except where we explicitly test the shipped PRBLX->PRILX
# alias, which is the production use case that motivated the feature.
# ---------------------------------------------------------------------------

def _dual_table() -> pd.DataFrame:
    return pd.DataFrame([
        # The "current holding" the user wants to replace — in scored universe.
        {"Symbol": "AAA", "Name": "Alpha Act", "Category": "Fake LargeBlend",
         "Fund_Type": "Active",
         "Score_2023_Final": 60.0, "Score_2025_Final": 45.0,
         "Score_Band_2023": "REVIEW", "Score_Band_2025": "WEAK",
         "Quadrant": "Q3_Only_2023", "Consensus_Rank": 7,
         "Score_Gap": -15.0, "Rank_2023": 4, "Rank_2025": 9,
         "Action_Flag": "DROP", "Primary_Driver": "x",
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0},
        # Same-category top candidate — consensus strong.
        {"Symbol": "BBB", "Name": "Beta Ix", "Category": "Fake LargeBlend",
         "Fund_Type": "Passive",
         "Score_2023_Final": 92.0, "Score_2025_Final": 90.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
         "Quadrant": "Q1_Both_Strong", "Consensus_Rank": 1,
         "Score_Gap": -2.0, "Rank_2023": 1, "Rank_2025": 2,
         "Action_Flag": "LEAD", "Primary_Driver": "y",
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0},
        # Same-category, performance-led (STRONG on 2023, softer on 2025).
        {"Symbol": "CCC", "Name": "Gamma Act", "Category": "Fake LargeBlend",
         "Fund_Type": "Active",
         "Score_2023_Final": 85.0, "Score_2025_Final": 70.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "REVIEW",
         "Quadrant": "Q3_Only_2023", "Consensus_Rank": 3,
         "Score_Gap": -15.0, "Rank_2023": 2, "Rank_2025": 5,
         "Action_Flag": "REVIEW", "Primary_Driver": "z",
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0},
        # Same-category, quality-led (STRONG on 2025, softer on 2023).
        {"Symbol": "DDD", "Name": "Delta Act", "Category": "Fake LargeBlend",
         "Fund_Type": "Active",
         "Score_2023_Final": 70.0, "Score_2025_Final": 88.0,
         "Score_Band_2023": "REVIEW", "Score_Band_2025": "STRONG",
         "Quadrant": "Q2_Only_2025", "Consensus_Rank": 2,
         "Score_Gap": 18.0, "Rank_2023": 5, "Rank_2025": 3,
         "Action_Flag": "LEAD", "Primary_Driver": "w",
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0},
        # Different category — must be excluded.
        {"Symbol": "EEE", "Name": "Epsilon Act", "Category": "Fake SmallValue",
         "Fund_Type": "Active",
         "Score_2023_Final": 95.0, "Score_2025_Final": 95.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
         "Quadrant": "Q1_Both_Strong", "Consensus_Rank": 1,
         "Score_Gap": 0.0, "Rank_2023": 1, "Rank_2025": 1,
         "Action_Flag": "LEAD", "Primary_Driver": "q",
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0},
        # Same-category replacement representative that lives in the scored
        # universe — this is the "alias target" used in the alias test below.
        {"Symbol": "SCOREA", "Name": "Alpha Core Ix (inst)", "Category": "Fake LargeBlend",
         "Fund_Type": "Passive",
         "Score_2023_Final": 80.0, "Score_2025_Final": 82.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
         "Quadrant": "Q1_Both_Strong", "Consensus_Rank": 4,
         "Score_Gap": 2.0, "Rank_2023": 3, "Rank_2025": 4,
         "Action_Flag": "LEAD", "Primary_Driver": "inst",
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0},
    ])


def _scorecard() -> pd.DataFrame:
    # Minimal shape mirroring model_holdings_overlay's scorecard output.
    return pd.DataFrame([
        {"Model_Name": "ModelX", "Symbol": "AAA",
         "Scoring_Symbol": "AAA", "Alias_Applied": False,
         "Target_Weight": 0.4, "Target_Weight_Pct": 40.0,
         "Overlay_Action": "Replacement_Candidate"},
        {"Model_Name": "ModelY", "Symbol": "BBB",
         "Scoring_Symbol": "BBB", "Alias_Applied": False,
         "Target_Weight": 0.3, "Target_Weight_Pct": 30.0,
         "Overlay_Action": "High_Conviction_Hold"},
    ])


# ---------------------------------------------------------------------------
# Core behavior
# ---------------------------------------------------------------------------

def test_category_inferred_from_universe_and_same_category_filter():
    result = build_replacement_workbench(
        _dual_table(), "AAA", top_n=10, alias_map={},
    )
    assert result.category == "Fake LargeBlend"
    assert result.category_source == "universe"
    # Every candidate is the same category; EEE (SmallValue) must be excluded.
    assert set(result.candidates["Category"]) == {"Fake LargeBlend"}
    assert "EEE" not in set(result.candidates["Symbol"])
    # Current ticker excluded from its own candidate pool.
    assert "AAA" not in set(result.candidates["Symbol"])


def test_candidates_are_ranked_by_consensus_and_preserve_dual_lens():
    # Legacy behavior pre-dates the inferred fund-type filter; opt out so
    # the test still exercises the cross-type ranking ordering.
    result = build_replacement_workbench(
        _dual_table(), "AAA", top_n=10, alias_map={},
        apply_fund_type_filter=False,
    )
    # Both 2023 and 2025 columns surface on every row — we don't collapse
    # disagreement.
    for col in ("Score_2023_Final", "Score_2025_Final",
                "Rank_2023", "Rank_2025",
                "Score_Band_2023", "Score_Band_2025",
                "Quadrant", "Reason_Label"):
        assert col in result.candidates.columns
    # Ranked by Consensus_Rank ascending -> BBB (1), DDD (2), CCC (3), SCOREA (4)
    ranks = list(result.candidates["Symbol"])
    assert ranks == ["BBB", "DDD", "CCC", "SCOREA"]
    assert list(result.candidates["Rank"]) == [1, 2, 3, 4]


def test_reason_labels_distinguish_perf_and_quality_led():
    result = build_replacement_workbench(
        _dual_table(), "AAA", top_n=10, alias_map={},
        apply_fund_type_filter=False,
    )
    by_sym = dict(zip(result.candidates["Symbol"], result.candidates["Reason_Label"]))
    assert "Consensus" in by_sym["BBB"]
    assert "Performance-led" in by_sym["CCC"]
    assert "Quality-led" in by_sym["DDD"]


def test_top_n_caps_candidate_count():
    result = build_replacement_workbench(
        _dual_table(), "AAA", top_n=2, alias_map={},
        apply_fund_type_filter=False,
    )
    assert len(result.candidates) == 2
    # Top-2 by consensus should be BBB (1) then DDD (2).
    assert list(result.candidates["Symbol"]) == ["BBB", "DDD"]


def test_category_override_when_current_missing_from_universe():
    result = build_replacement_workbench(
        _dual_table(), "NOTINUNIV",
        category_override="Fake LargeBlend", top_n=10, alias_map={},
    )
    assert result.category == "Fake LargeBlend"
    assert result.category_source == "override"
    assert not result.candidates.empty


def test_unknown_ticker_without_override_yields_no_candidates():
    result = build_replacement_workbench(
        _dual_table(), "NOTINUNIV", top_n=10, alias_map={},
    )
    assert result.category is None
    assert result.category_source == "unknown"
    assert result.candidates.empty
    assert result.summary["current_in_universe"] is False


# ---------------------------------------------------------------------------
# Alias reconciliation — the PRBLX/PRILX use case (sanitized analogue).
# ---------------------------------------------------------------------------

def test_alias_resolves_share_class_to_scored_row():
    # ALIASA is not in the dual table, but resolves to SCOREA via alias.
    alias_map = {"ALIASA": "SCOREA"}
    result = build_replacement_workbench(
        _dual_table(), "ALIASA",
        alias_map=alias_map, top_n=10,
    )
    assert result.ticker == "ALIASA"
    assert result.resolved_ticker == "SCOREA"
    assert result.alias_applied is True
    # Category pulled from universe via the resolved symbol.
    assert result.category == "Fake LargeBlend"
    assert result.category_source == "universe"
    # SCOREA is the resolved holding; it should be excluded from its own
    # candidate pool.
    assert "SCOREA" not in set(result.candidates["Symbol"])
    # Profile carries both the committee-facing original and the resolved symbol.
    prof = result.current_profile.iloc[0]
    assert prof["Symbol"] == "ALIASA"
    assert prof["Scoring_Symbol"] == "SCOREA"
    assert bool(prof["Alias_Applied"]) is True
    assert prof["Name"] == "Alpha Core Ix (inst)"


def test_default_alias_handles_prblx_to_prilx():
    """The committee-facing use case: PRBLX maps to PRILX without a custom map."""
    universe = pd.DataFrame([
        {"Symbol": "PRILX", "Name": "Parnassus Core (inst)",
         "Category": "Large Blend", "Fund_Type": "Active",
         "Score_2023_Final": 70.0, "Score_2025_Final": 65.0,
         "Score_Band_2023": "REVIEW", "Score_Band_2025": "REVIEW",
         "Quadrant": "Q4_Both_Weak", "Consensus_Rank": 25,
         "Score_Gap": -5.0, "Rank_2023": 20, "Rank_2025": 30,
         "Action_Flag": "REVIEW", "Primary_Driver": "x",
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0},
        {"Symbol": "BBBLB", "Name": "Other Large Blend",
         "Category": "Large Blend", "Fund_Type": "Active",
         "Score_2023_Final": 90.0, "Score_2025_Final": 92.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
         "Quadrant": "Q1_Both_Strong", "Consensus_Rank": 1,
         "Score_Gap": 2.0, "Rank_2023": 1, "Rank_2025": 1,
         "Action_Flag": "LEAD", "Primary_Driver": "y",
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0},
    ])
    # Omit alias_map to force load of the shipped defaults (PRBLX -> PRILX).
    result = build_replacement_workbench(universe, "PRBLX", top_n=5)
    assert result.ticker == "PRBLX"
    assert result.resolved_ticker == "PRILX"
    assert result.alias_applied is True
    assert result.category == "Large Blend"
    assert set(result.candidates["Symbol"]) == {"BBBLB"}


# ---------------------------------------------------------------------------
# Already-held flagging / exclude-held toggle.
# ---------------------------------------------------------------------------

def test_already_held_flag_set_when_scorecard_provided():
    result = build_replacement_workbench(
        _dual_table(), "AAA",
        scorecard=_scorecard(), top_n=10, alias_map={},
        apply_fund_type_filter=False,
    )
    rows = result.candidates.set_index("Symbol")
    # BBB is held by ModelY in the scorecard.
    assert bool(rows.loc["BBB", "Already_Held"]) is True
    assert "ModelY" in str(rows.loc["BBB", "Held_By_Models"])
    # CCC / DDD / SCOREA are not held.
    for sym in ("CCC", "DDD", "SCOREA"):
        assert bool(rows.loc[sym, "Already_Held"]) is False


def test_exclude_held_drops_held_rows():
    result = build_replacement_workbench(
        _dual_table(), "AAA",
        scorecard=_scorecard(), top_n=10, exclude_held=True, alias_map={},
        apply_fund_type_filter=False,
    )
    # BBB is held and must be removed when exclude_held=True.
    assert "BBB" not in set(result.candidates["Symbol"])
    # But CCC / DDD / SCOREA remain.
    assert {"CCC", "DDD", "SCOREA"}.issubset(set(result.candidates["Symbol"]))


# ---------------------------------------------------------------------------
# Current holding profile augmentation from scorecard.
# ---------------------------------------------------------------------------

def test_profile_augmented_with_model_fields_when_scorecard_present():
    result = build_replacement_workbench(
        _dual_table(), "AAA",
        scorecard=_scorecard(), top_n=3, alias_map={},
    )
    prof = result.current_profile.iloc[0]
    assert prof["Model_Name"] == "ModelX"
    assert prof["Target_Weight_Pct"] == pytest.approx(40.0)
    assert prof["Overlay_Action"] == "Replacement_Candidate"
    assert bool(prof["Scored_In_Universe"]) is True


# ---------------------------------------------------------------------------
# Determinism + persistence.
# ---------------------------------------------------------------------------

def test_workbench_is_deterministic():
    a = build_replacement_workbench(_dual_table(), "AAA", top_n=10, alias_map={})
    b = build_replacement_workbench(_dual_table(), "AAA", top_n=10, alias_map={})
    pd.testing.assert_frame_equal(a.candidates, b.candidates)
    pd.testing.assert_frame_equal(a.current_profile, b.current_profile)
    # summary contains a timestamp; compare structural keys only.
    assert a.summary["candidate_count"] == b.summary["candidate_count"]
    assert a.summary["category"] == b.summary["category"]


def test_write_and_load_roundtrip():
    result = build_replacement_workbench(
        _dual_table(), "AAA", top_n=5, alias_map={},
    )
    with tempfile.TemporaryDirectory() as tmp:
        paths = write_replacement(result, tmp)
        for key in ("candidates", "current_profile", "summary", "brief"):
            assert os.path.isfile(paths[key])
        loaded = load_replacement(tmp)
        assert loaded is not None
        # CSV roundtrip mutates empty-string columns to NaN and can coerce
        # bools to py-bool/str — compare on the stable structural columns only.
        assert list(loaded["candidates"]["Symbol"]) == list(result.candidates["Symbol"])
        assert list(loaded["candidates"]["Rank"]) == list(result.candidates["Rank"])
        assert list(loaded["candidates"]["Score_2023_Final"]) == \
            list(result.candidates["Score_2023_Final"])
        assert list(loaded["candidates"]["Score_2025_Final"]) == \
            list(result.candidates["Score_2025_Final"])
        assert loaded["summary"]["ticker"] == "AAA"
        assert "# Replacement Workbench — AAA" in loaded["brief_markdown"]


def test_load_replacement_returns_none_when_empty():
    with tempfile.TemporaryDirectory() as tmp:
        assert load_replacement(tmp) is None
    assert load_replacement("/no/such/dir/ever") is None


def test_workbench_dir_layout():
    path = workbench_dir("/some/runs", "2026-04-30", "prblx")
    # Ticker always normalized to uppercase, single-ticker subfolder.
    assert path == os.path.join(
        "/some/runs", "2026-04-30", WORKBENCH_SUBDIR, "PRBLX",
    )


# ---------------------------------------------------------------------------
# Brief + summary content.
# ---------------------------------------------------------------------------

def test_brief_markdown_mentions_category_and_candidates():
    result = build_replacement_workbench(
        _dual_table(), "AAA", top_n=3, alias_map={},
        apply_fund_type_filter=False,
    )
    md = result.brief_markdown
    assert "Replacement Workbench — AAA" in md
    assert "Fake LargeBlend" in md
    # Top candidate symbol must be cited in the markdown table.
    assert "BBB" in md
    # Dual-lens visibility: both bands appear as column header.
    assert "Bands" in md
    assert "Reason" in md


def test_summary_captures_provenance_fields():
    result = build_replacement_workbench(
        _dual_table(), "AAA", top_n=5, alias_map={}, run_date="2026-04-30",
    )
    s = result.summary
    assert s["ticker"] == "AAA"
    assert s["resolved_ticker"] == "AAA"
    assert s["run_date"] == "2026-04-30"
    assert s["category"] == "Fake LargeBlend"
    assert s["category_source"] == "universe"
    assert s["candidate_count"] == len(result.candidates)
    assert s["current_in_universe"] is True


# ---------------------------------------------------------------------------
# High-level convenience wrapper against an archived run.
# ---------------------------------------------------------------------------

def test_run_replacement_for_run_persists_artifacts_under_archive(tmp_path):
    # Build a tiny archive on disk with the dual-score table + metadata.
    from run_archive import create_run_archive

    runs_dir = str(tmp_path / "runs")
    run_date = "2026-04-30"
    create_run_archive(
        run_date=run_date,
        runs_dir=runs_dir,
        table=_dual_table(),
    )

    bundle = run_replacement_for_run(
        run_date=run_date,
        ticker="AAA",
        runs_dir=runs_dir,
        top_n=5,
        persist=True,
    )
    assert bundle["run_date"] == run_date
    expected_dir = workbench_dir(runs_dir, run_date, "AAA")
    assert bundle["path"] == expected_dir
    assert os.path.isdir(expected_dir)
    for name in (CANDIDATES_NAME, CURRENT_PROFILE_NAME, SUMMARY_NAME, BRIEF_NAME):
        assert os.path.isfile(os.path.join(expected_dir, name))

    # Reload and verify round-trip.
    loaded = load_replacement(expected_dir)
    assert loaded is not None
    assert loaded["summary"]["run_date"] == run_date
    assert not loaded["candidates"].empty
