"""Tests for model_holdings_overlay."""

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

from model_holdings_overlay import (  # noqa: E402
    ACTION_HIGH_CONVICTION,
    ACTION_PERF_LED,
    ACTION_QUALITY_LED,
    ACTION_REPLACEMENT,
    ACTION_REVIEW_COVERAGE,
    METADATA_NAME,
    OVERLAY_SUBDIR,
    RESEARCH_CANDIDATES_NAME,
    REPLACEMENT_CANDIDATES_NAME,
    SCORECARD_NAME,
    SUMMARY_NAME,
    CURRENT_REVIEW_NAME,
    build_model_overlay,
    load_overlay,
    write_overlay,
)


# ---------------------------------------------------------------------------
# Synthetic dual-score table — small, deterministic, and covers every
# band / quadrant combination the action-flag logic needs.
# ---------------------------------------------------------------------------

def _dual_table():
    return pd.DataFrame([
        # Symbol, Name, Cat, Fund_Type, s2023, s2025, band23, band25, quad, cons
        {"Symbol": "AAA", "Name": "Alpha Ix", "Category": "LargeBlend",
         "Fund_Type": "Passive", "Score_2023_Final": 90.0, "Score_2025_Final": 90.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
         "Quadrant": "Q1_Both_Strong", "Consensus_Rank": 1,
         "Score_Gap": 0.0, "Rank_2023": 1, "Rank_2025": 1,
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0,
         "Primary_Driver": "Stable"},
        {"Symbol": "BBB", "Name": "Beta Act", "Category": "LargeBlend",
         "Fund_Type": "Active", "Score_2023_Final": 85.0, "Score_2025_Final": 55.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "WEAK",
         "Quadrant": "Q3_Only_2023", "Consensus_Rank": 5,
         "Score_Gap": -30.0, "Rank_2023": 2, "Rank_2025": 8,
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0,
         "Primary_Driver": "Downgraded by 2025 system"},
        {"Symbol": "CCC", "Name": "Gamma Act", "Category": "SmallValue",
         "Fund_Type": "Active", "Score_2023_Final": 50.0, "Score_2025_Final": 85.0,
         "Score_Band_2023": "WEAK", "Score_Band_2025": "STRONG",
         "Quadrant": "Q2_Only_2025", "Consensus_Rank": 4,
         "Score_Gap": 35.0, "Rank_2023": 6, "Rank_2025": 2,
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0,
         "Primary_Driver": "Upgraded by 2025 system"},
        {"Symbol": "DDD", "Name": "Delta Act", "Category": "LargeBlend",
         "Fund_Type": "Active", "Score_2023_Final": 30.0, "Score_2025_Final": 25.0,
         "Score_Band_2023": "WEAK", "Score_Band_2025": "WEAK",
         "Quadrant": "Q4_Both_Weak", "Consensus_Rank": 9,
         "Score_Gap": -5.0, "Rank_2023": 8, "Rank_2025": 9,
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0,
         "Primary_Driver": "Stable"},
        # Unheld candidate funds in each category, to make research +
        # replacement lists non-empty.
        {"Symbol": "EEE", "Name": "Epsilon Ix", "Category": "LargeBlend",
         "Fund_Type": "Passive", "Score_2023_Final": 88.0, "Score_2025_Final": 87.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
         "Quadrant": "Q1_Both_Strong", "Consensus_Rank": 2,
         "Score_Gap": -1.0, "Rank_2023": 3, "Rank_2025": 3,
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0,
         "Primary_Driver": "Stable"},
        {"Symbol": "FFF", "Name": "Zeta Act", "Category": "SmallValue",
         "Fund_Type": "Active", "Score_2023_Final": 82.0, "Score_2025_Final": 83.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
         "Quadrant": "Q1_Both_Strong", "Consensus_Rank": 3,
         "Score_Gap": 1.0, "Rank_2023": 4, "Rank_2025": 4,
         "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0,
         "Primary_Driver": "Stable"},
    ])


def _holdings():
    return pd.DataFrame([
        {"Model_Name": "Moderate", "Symbol": "AAA", "Target_Weight": "40%",
         "Fund_Name": "Alpha Ix"},
        {"Model_Name": "Moderate", "Symbol": "BBB", "Target_Weight": "30%"},
        {"Model_Name": "Moderate", "Symbol": "CCC", "Target_Weight": "20%"},
        {"Model_Name": "Moderate", "Symbol": "DDD", "Target_Weight": "10%"},
        {"Model_Name": "Aggressive", "Symbol": "AAA", "Target_Weight": "50%"},
        {"Model_Name": "Aggressive", "Symbol": "XXX", "Target_Weight": "50%"},  # unscored
    ])


# ---------------------------------------------------------------------------
# Core behavior
# ---------------------------------------------------------------------------

def test_scorecard_assigns_expected_actions():
    result = build_model_overlay(_holdings(), _dual_table())
    sc = result.scorecard
    # Map (Model,Symbol) to Overlay_Action for easier assertion.
    m = {(r.Model_Name, r.Symbol): r.Overlay_Action for r in sc.itertuples()}
    assert m[("Moderate", "AAA")] == ACTION_HIGH_CONVICTION
    assert m[("Moderate", "BBB")] == ACTION_PERF_LED
    assert m[("Moderate", "CCC")] == ACTION_QUALITY_LED
    assert m[("Moderate", "DDD")] == ACTION_REPLACEMENT
    assert m[("Aggressive", "AAA")] == ACTION_HIGH_CONVICTION
    assert m[("Aggressive", "XXX")] == ACTION_REVIEW_COVERAGE


def test_summary_weighted_scores_match_manual_calc():
    result = build_model_overlay(_holdings(), _dual_table())
    summary = result.summary.set_index("Model_Name")
    # Moderate: (0.4*90 + 0.3*85 + 0.2*50 + 0.1*30) / 1.0 = 74.5 for 2023
    assert summary.loc["Moderate", "Weighted_Score_2023"] == pytest.approx(74.5)
    # 2025: 0.4*90 + 0.3*55 + 0.2*85 + 0.1*25 = 72.0
    assert summary.loc["Moderate", "Weighted_Score_2025"] == pytest.approx(72.0)
    # Aggressive has only AAA scored; weighted 2023 over scored = 90 (XXX excluded)
    assert summary.loc["Aggressive", "Weighted_Score_2023"] == pytest.approx(90.0)
    # Unscored weight ~50% for Aggressive
    assert summary.loc["Aggressive", "Weight_Pct_Unscored"] == pytest.approx(50.0, abs=0.01)


def test_current_review_excludes_high_conviction():
    result = build_model_overlay(_holdings(), _dual_table())
    actions = set(result.current_review["Overlay_Action"])
    assert ACTION_HIGH_CONVICTION not in actions
    # Should include replacement, perf-led, quality-led, review-coverage.
    assert ACTION_REPLACEMENT in actions
    assert ACTION_PERF_LED in actions
    assert ACTION_QUALITY_LED in actions


def test_research_candidates_exclude_held_symbols():
    result = build_model_overlay(_holdings(), _dual_table())
    held = set(_holdings()["Symbol"])
    assert set(result.research_candidates["Symbol"]).isdisjoint(held)
    # Only STRONG-band funds show up as research candidates.
    for _, row in result.research_candidates.iterrows():
        assert row["Score_Band_2023"] == "STRONG" or row["Score_Band_2025"] == "STRONG"


def test_replacement_candidates_are_same_category():
    result = build_model_overlay(_holdings(), _dual_table())
    rep = result.replacement_candidates
    assert not rep.empty
    # Only DDD (LargeBlend) is a replacement target in the fixture.
    assert set(rep["Current_Symbol"]) == {"DDD"}
    assert (rep["Current_Category"] == rep["Candidate_Category"]).all()
    # EEE is the only unheld LargeBlend candidate with STRONG/STRONG.
    assert "EEE" in set(rep["Candidate_Symbol"])


def test_overlay_deterministic():
    a = build_model_overlay(_holdings(), _dual_table())
    b = build_model_overlay(_holdings(), _dual_table())
    pd.testing.assert_frame_equal(a.scorecard, b.scorecard)
    pd.testing.assert_frame_equal(a.summary, b.summary)
    pd.testing.assert_frame_equal(a.research_candidates, b.research_candidates)
    pd.testing.assert_frame_equal(a.replacement_candidates, b.replacement_candidates)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_write_and_load_roundtrip():
    result = build_model_overlay(_holdings(), _dual_table())
    with tempfile.TemporaryDirectory() as tmp:
        paths = write_overlay(result, tmp)
        for key in ("scorecard", "summary", "current_review",
                    "research_candidates", "replacement_candidates",
                    "metadata"):
            assert os.path.isfile(paths[key])
        loaded = load_overlay(tmp)
        assert loaded is not None
        pd.testing.assert_frame_equal(
            loaded["scorecard"].reset_index(drop=True),
            result.scorecard.reset_index(drop=True),
        )
        assert loaded["metadata"]["holding_row_count"] == len(result.scorecard)


def test_load_overlay_returns_none_when_empty():
    with tempfile.TemporaryDirectory() as tmp:
        assert load_overlay(tmp) is None
    assert load_overlay("/no/such/dir/ever") is None


def test_unknown_symbol_sinks_to_review_missing_score():
    holdings = pd.DataFrame([
        {"Model_Name": "X", "Symbol": "NOTIN", "Target_Weight": 1.0},
    ])
    result = build_model_overlay(holdings, _dual_table())
    assert result.scorecard.iloc[0]["Overlay_Action"] == ACTION_REVIEW_COVERAGE
    assert bool(result.scorecard.iloc[0]["Scored_In_Universe"]) is False


# ---------------------------------------------------------------------------
# Share-class alias reconciliation
# ---------------------------------------------------------------------------

SANITIZED_ALIASES = {"ALIASA": "AAA"}  # AAA lives in the fixture dual table


def test_alias_resolves_share_class_to_scored_row():
    # ALIASA is not in the dual table, but resolves to AAA via alias.
    holdings = pd.DataFrame([
        {"Model_Name": "M", "Symbol": "ALIASA", "Target_Weight": 1.0},
    ])
    result = build_model_overlay(
        holdings, _dual_table(), alias_map=SANITIZED_ALIASES,
    )
    row = result.scorecard.iloc[0]
    # Committee-facing Symbol is preserved.
    assert row["Symbol"] == "ALIASA"
    # Scoring_Symbol is the resolved ticker used for the join.
    assert row["Scoring_Symbol"] == "AAA"
    assert bool(row["Alias_Applied"]) is True
    assert bool(row["Scored_In_Universe"]) is True
    # And the overlay action reflects the joined score, not missing coverage.
    assert row["Overlay_Action"] == ACTION_HIGH_CONVICTION
    # Metadata surfaces the alias usage.
    assert result.metadata["alias_applied_rows"] == 1
    pairs = result.metadata["alias_pairs"]
    assert {p["original"]: p["scoring"] for p in pairs} == {"ALIASA": "AAA"}


def test_aliased_symbol_excluded_from_research_candidates():
    # If ALIASA resolves to AAA and AAA is held, AAA must not appear in
    # research candidates (otherwise we'd recommend a fund we already own).
    holdings = pd.DataFrame([
        {"Model_Name": "M", "Symbol": "ALIASA", "Target_Weight": 1.0},
    ])
    result = build_model_overlay(
        holdings, _dual_table(), alias_map=SANITIZED_ALIASES,
    )
    assert "AAA" not in set(result.research_candidates["Symbol"])


def test_original_symbol_in_universe_not_overridden_by_alias():
    # Existing fixture symbol CCC is in the dual table. Mapping CCC->DDD
    # must NOT take effect because CCC is already valid.
    holdings = pd.DataFrame([
        {"Model_Name": "M", "Symbol": "CCC", "Target_Weight": 1.0},
    ])
    result = build_model_overlay(
        holdings, _dual_table(), alias_map={"CCC": "DDD"},
    )
    row = result.scorecard.iloc[0]
    assert row["Symbol"] == "CCC"
    assert row["Scoring_Symbol"] == "CCC"
    assert bool(row["Alias_Applied"]) is False


def test_replacement_candidates_surface_current_scoring_symbol():
    # DDD is Q4_Both_Weak in the fixture. Holding it via alias ALIASD should
    # still produce replacement candidates, and the output row must carry
    # both Current_Symbol (ALIASD) and Current_Scoring_Symbol (DDD).
    holdings = pd.DataFrame([
        {"Model_Name": "M", "Symbol": "ALIASD", "Target_Weight": 1.0},
    ])
    result = build_model_overlay(
        holdings, _dual_table(), alias_map={"ALIASD": "DDD"},
    )
    rep = result.replacement_candidates
    assert not rep.empty
    assert set(rep["Current_Symbol"]) == {"ALIASD"}
    assert set(rep["Current_Scoring_Symbol"]) == {"DDD"}
