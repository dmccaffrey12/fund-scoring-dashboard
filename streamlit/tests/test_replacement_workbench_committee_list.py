"""Tests for the committee-candidate-list path through the replacement
workbench.

Covers the PRBLX-replacement flow described in the user's escalation:

    * Uploaded committee candidate list is the *authoritative* universe
      for the staff-facing brief — full-category discovery is suppressed.
    * Already-held passive sleeve names (SPYM-style) are excluded by
      default, with a clear, surfaced list rather than a silent drop.
    * Names from the committee list win over candidate-exposures names,
      which in turn win over the scored-universe name.
    * Committee-list symbols missing from the scored universe still land
      in the candidate table, marked un-scored.
    * The printable Markdown brief calls out the committee list as the
      universe, prominently.
"""

from __future__ import annotations

import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_STREAMLIT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _STREAMLIT_DIR not in sys.path:
    sys.path.insert(0, _STREAMLIT_DIR)

from candidate_list_intake import parse_candidate_list  # noqa: E402
from exposure_intake import parse_exposures  # noqa: E402
from printable_brief import render_printable_brief_html  # noqa: E402
from replacement_workbench import (  # noqa: E402
    build_replacement_workbench,
)


FIX_DIR = os.path.join(_HERE, "fixtures")


def _fix(name: str) -> str:
    return os.path.join(FIX_DIR, name)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _dual_table() -> pd.DataFrame:
    """Mirrors the curated-test universe — adds an extra passive sleeve
    PASSV that scores #1, plus several active ideas to choose from."""
    return pd.DataFrame([
        {"Symbol": "LLLA", "Name": "Large Blend Active",
         "Category": "Large Blend", "Fund_Type": "Active",
         "Score_2023_Final": 60.0, "Score_2025_Final": 65.0,
         "Score_Band_2023": "REVIEW", "Score_Band_2025": "REVIEW",
         "Quadrant": "Q4_Mid", "Consensus_Rank": 5,
         "Score_Gap": 5.0, "Rank_2023": 5, "Rank_2025": 5,
         "Action_Flag": "REVIEW", "Primary_Driver": "x"},
        {"Symbol": "CAND_FIT", "Name": "Stale Scored-Universe Name",
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
        {"Symbol": "CAND_MID", "Name": "Decent Mid Lean",
         "Category": "Large Blend", "Fund_Type": "Active",
         "Score_2023_Final": 80.0, "Score_2025_Final": 78.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "REVIEW",
         "Quadrant": "Q3_Only_2023", "Consensus_Rank": 2,
         "Score_Gap": -2.0, "Rank_2023": 2, "Rank_2025": 4,
         "Action_Flag": "REVIEW", "Primary_Driver": "w"},
        # Extra scored-universe-but-irrelevant active fund. Should never
        # appear when the committee list is supplied.
        {"Symbol": "SAME_CAT_NOISE", "Name": "Some Other Active",
         "Category": "Large Blend", "Fund_Type": "Active",
         "Score_2023_Final": 88.0, "Score_2025_Final": 88.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
         "Quadrant": "Q1_Both_Strong", "Consensus_Rank": 4,
         "Score_Gap": 0.0, "Rank_2023": 4, "Rank_2025": 2,
         "Action_Flag": "LEAD", "Primary_Driver": "noise"},
        # Passive sleeve (SPYM analogue) — already held, scored #1.
        {"Symbol": "PASSV", "Name": "Big Passive Index ETF",
         "Category": "Large Blend", "Fund_Type": "Passive",
         "Score_2023_Final": 99.0, "Score_2025_Final": 99.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
         "Quadrant": "Q1_Both_Strong", "Consensus_Rank": 0,
         "Score_Gap": 0.0, "Rank_2023": 0, "Rank_2025": 0,
         "Action_Flag": "LEAD", "Primary_Driver": "passive"},
    ])


def _scorecard_with_passive_held() -> pd.DataFrame:
    return pd.DataFrame([
        {"Model_Name": "100/0", "Symbol": s, "Scoring_Symbol": s}
        for s in ("LLLA", "PASSV")
    ])


def _committee_list_df() -> pd.DataFrame:
    """Three active candidates the committee actually wants discussed."""
    return parse_candidate_list(pd.DataFrame({
        "Ticker": ["CAND_FIT", "CAND_DRIFT", "CAND_MID"],
        "Name": [
            "Curated Best-Fit Active Fund",
            "Curated Off-Bench Growth",
            "Curated Mid Lean",
        ],
        "Notes": ["preferred", "highest-conviction", "diversifier"],
    }))


# ---------------------------------------------------------------------------
# Authoritative-universe behavior
# ---------------------------------------------------------------------------

def test_committee_list_is_authoritative_universe_by_default():
    """Committee list supplied → staff-facing candidates restricted to it.
    Same-category discovery picks (SAME_CAT_NOISE) and already-held passive
    (PASSV) must NOT appear."""
    result = build_replacement_workbench(
        _dual_table(), "LLLA",
        top_n=10, alias_map={},
        scorecard=_scorecard_with_passive_held(),
        candidate_list=_committee_list_df(),
    )
    syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    assert set(syms) == {"CAND_FIT", "CAND_DRIFT", "CAND_MID"}
    assert "PASSV" not in syms
    assert "SAME_CAT_NOISE" not in syms

    summary = result.summary
    assert summary["candidate_universe_source"] == "committee_list"
    assert summary["committee_list_supplied"] is True
    assert summary["committee_list_size"] == 3
    assert summary["restrict_to_candidate_exposures"] is True
    assert summary["exclude_already_held"] is True


def test_committee_list_wins_over_candidate_exposures_for_universe():
    """When BOTH a committee list and a candidate-exposures file are
    supplied, the committee list defines the universe (FundScore + brief).
    The exposure file is still used for benchmark-fit metrics where
    available."""
    cand_exp = parse_exposures(_fix("exposures_candidates_good.csv")).copy()
    # Add a noise row to the exposure file that is NOT on the committee list.
    extra = cand_exp.iloc[0:1].copy()
    extra["Symbol"] = "EXP_ONLY_NOISE"
    extra["Name"] = "Should Not Appear"
    cand_exp = pd.concat([cand_exp, extra], ignore_index=True)

    cl = parse_candidate_list(pd.DataFrame({
        "Symbol": ["CAND_FIT"],
        "Name": ["Committee-List Top Pick"],
    }))
    result = build_replacement_workbench(
        _dual_table(), "LLLA",
        top_n=10, alias_map={},
        scorecard=_scorecard_with_passive_held(),
        model_holdings=pd.DataFrame([
            {"Model_Name": "100/0", "Symbol": "LLLA", "Target_Weight": 0.5},
            {"Model_Name": "100/0", "Symbol": "PASSV", "Target_Weight": 0.5},
        ]),
        model_exposures=parse_exposures(_fix("exposures_model_good.csv")),
        benchmark_exposures=parse_exposures(_fix("exposures_bench_good.csv")),
        benchmark_weights={"LLLA": 0.5, "PASSV": 0.5},
        candidate_exposures=cand_exp,
        candidate_list=cl,
    )
    syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    assert syms == ["CAND_FIT"]
    assert "EXP_ONLY_NOISE" not in syms

    bf = result.benchmark_fit_candidates
    bf_syms = bf["Candidate_Symbol"].astype(str).str.upper().tolist() \
        if not bf.empty else []
    assert "EXP_ONLY_NOISE" not in bf_syms
    # Bench-fit ranking is also restricted to the committee universe.
    assert set(bf_syms).issubset({"CAND_FIT"})


def test_committee_list_names_win_over_exposures_and_scored_universe():
    """Display name precedence: committee_list > candidate_exposures >
    scored universe."""
    cand_exp = parse_exposures(_fix("exposures_candidates_good.csv")).copy()
    cand_exp.loc[cand_exp["Symbol"] == "CAND_FIT", "Name"] = (
        "Exposure-File Name (should lose)"
    )
    cl = parse_candidate_list(pd.DataFrame({
        "Symbol": ["CAND_FIT"],
        "Name": ["Committee-List Name (should win)"],
    }))
    result = build_replacement_workbench(
        _dual_table(), "LLLA",
        top_n=10, alias_map={},
        candidate_exposures=cand_exp,
        candidate_list=cl,
    )
    row = result.candidates.iloc[0]
    assert row["Name"] == "Committee-List Name (should win)"


def test_already_held_committee_list_member_is_excluded_with_messaging():
    """When the user uploads a committee list that *includes* a held name
    like PASSV, the default keeps PASSV out of the candidate table and
    surfaces it via committee_list_excluded_held_symbols. The name is
    NOT silently dropped."""
    cl = parse_candidate_list(pd.DataFrame({
        "Symbol": ["CAND_FIT", "PASSV"],
        "Name": ["Active Idea", "Held Passive"],
    }))
    result = build_replacement_workbench(
        _dual_table(), "LLLA",
        top_n=10, alias_map={},
        scorecard=_scorecard_with_passive_held(),
        candidate_list=cl,
    )
    syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    assert "PASSV" not in syms
    assert result.summary["committee_list_excluded_held_symbols"] == ["PASSV"]


def test_already_held_committee_list_member_kept_with_include_override():
    """exclude_already_held=False with a committee list that includes a
    held name keeps the held name in the table, flagged Already_Held, with
    the curated committee-list display name."""
    cl = parse_candidate_list(pd.DataFrame({
        "Symbol": ["CAND_FIT", "PASSV"],
        "Name": ["Active Idea", "User-Confirmed Passive Override"],
    }))
    result = build_replacement_workbench(
        _dual_table(), "LLLA",
        top_n=10, alias_map={},
        scorecard=_scorecard_with_passive_held(),
        candidate_list=cl,
        exclude_already_held=False,
    )
    syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    assert "PASSV" in syms
    passv_row = result.candidates.loc[
        result.candidates["Symbol"].astype(str).str.upper() == "PASSV"
    ].iloc[0]
    assert bool(passv_row["Already_Held"]) is True
    assert passv_row["Name"] == "User-Confirmed Passive Override"


def test_committee_list_symbol_missing_from_scored_universe_is_kept_unscored():
    """Symbols on the committee list that aren't in the scored universe
    must still appear in the candidate table — they just land as un-scored
    rows, with a Reason_Label that explains the gap."""
    cl = parse_candidate_list(pd.DataFrame({
        "Symbol": ["CAND_FIT", "BRAND_NEW_FUND"],
        "Name": ["Curated Idea", "Not Yet Scored"],
    }))
    result = build_replacement_workbench(
        _dual_table(), "LLLA",
        top_n=10, alias_map={},
        candidate_list=cl,
    )
    syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    assert "BRAND_NEW_FUND" in syms
    new_row = result.candidates.loc[
        result.candidates["Symbol"].astype(str).str.upper() == "BRAND_NEW_FUND"
    ].iloc[0]
    assert bool(new_row["Scored_In_Universe"]) is False
    assert "scored universe" in str(new_row["Reason_Label"]).lower()
    assert (
        "BRAND_NEW_FUND"
        in result.summary["committee_list_missing_from_scored_universe"]
    )


def test_no_fallback_to_full_universe_when_committee_list_supplied():
    """No silent fallback: even if the committee list happens to contain
    only one symbol, the brief MUST NOT pad with same-category discovery
    picks like SAME_CAT_NOISE."""
    cl = parse_candidate_list(pd.DataFrame({"Symbol": ["CAND_FIT"]}))
    result = build_replacement_workbench(
        _dual_table(), "LLLA",
        top_n=10, alias_map={},
        candidate_list=cl,
    )
    syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    assert syms == ["CAND_FIT"]
    assert "SAME_CAT_NOISE" not in syms
    assert "PASSV" not in syms


def test_brief_labels_committee_list_universe_prominently():
    cl = _committee_list_df()
    result = build_replacement_workbench(
        _dual_table(), "LLLA",
        top_n=10, alias_map={},
        scorecard=_scorecard_with_passive_held(),
        candidate_list=cl,
    )
    md = result.brief_markdown
    assert "committee candidate list" in md.lower()
    # The size must surface so a reader can sanity-check the universe.
    assert "3 symbol" in md or "(3 symbol(s))" in md


def test_printable_html_brief_marks_universe_as_committee_list():
    cl = _committee_list_df()
    result = build_replacement_workbench(
        _dual_table(), "LLLA",
        top_n=10, alias_map={},
        scorecard=_scorecard_with_passive_held(),
        candidate_list=cl,
    )
    out = render_printable_brief_html(result)
    assert "Candidate universe" in out
    assert "committee candidate list" in out.lower()
    # The discovery-mode banner must NOT appear when the committee list
    # is the source — that wording was the original committee complaint.
    assert "discovery mode" not in out.lower()


def test_printable_html_brief_marks_discovery_mode_when_no_committee_list():
    # No committee list, no candidate exposures → discovery-mode banner.
    result = build_replacement_workbench(
        _dual_table(), "LLLA", top_n=5, alias_map={},
    )
    out = render_printable_brief_html(result)
    assert "discovery mode" in out.lower()
    assert "committee candidate list" in out.lower()  # nudge to upload one


def test_alignment_of_committee_list_with_candidate_exposures():
    """Benchmark-fit rows should align to the committee universe — symbols
    in the exposure file but absent from the committee list never appear in
    the bench-fit ranking."""
    cand_exp = parse_exposures(_fix("exposures_candidates_good.csv"))
    cl = parse_candidate_list(pd.DataFrame({"Symbol": ["CAND_FIT"]}))
    result = build_replacement_workbench(
        _dual_table(), "LLLA",
        top_n=10, alias_map={},
        scorecard=_scorecard_with_passive_held(),
        model_holdings=pd.DataFrame([
            {"Model_Name": "100/0", "Symbol": "LLLA", "Target_Weight": 0.5},
            {"Model_Name": "100/0", "Symbol": "PASSV", "Target_Weight": 0.5},
        ]),
        model_exposures=parse_exposures(_fix("exposures_model_good.csv")),
        benchmark_exposures=parse_exposures(_fix("exposures_bench_good.csv")),
        benchmark_weights={"LLLA": 0.5, "PASSV": 0.5},
        candidate_exposures=cand_exp,
        candidate_list=cl,
    )
    bf = result.benchmark_fit_candidates
    if not bf.empty:
        bf_syms = bf["Candidate_Symbol"].astype(str).str.upper().tolist()
        assert set(bf_syms).issubset({"CAND_FIT"})


def test_from_committee_list_flag_set_on_candidates():
    cl = _committee_list_df()
    result = build_replacement_workbench(
        _dual_table(), "LLLA", top_n=10, alias_map={},
        candidate_list=cl,
    )
    # All staff-facing rows are from the committee list.
    assert all(bool(v) for v in result.candidates["From_Committee_List"])


def test_uploaded_mode_with_only_committee_list_and_no_exposures():
    """Edge case: candidate_universe_mode='uploaded' + committee list only
    should still scope correctly (no fallback to the scored universe)."""
    cl = parse_candidate_list(pd.DataFrame({"Symbol": ["CAND_DRIFT"]}))
    result = build_replacement_workbench(
        _dual_table(), "LLLA", top_n=10, alias_map={},
        candidate_list=cl,
        candidate_universe_mode="uploaded",
    )
    syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    assert syms == ["CAND_DRIFT"]
    assert result.summary["candidate_universe_source"] == "committee_list"
