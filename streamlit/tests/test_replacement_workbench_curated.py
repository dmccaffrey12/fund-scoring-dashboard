"""Tests for the curated-universe + exclude-already-held behavior in
replacement_workbench. Adds coverage for the SPYM-shouldn't-double-up case
described in PR #18 review feedback.
"""

from __future__ import annotations

import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_STREAMLIT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _STREAMLIT_DIR not in sys.path:
    sys.path.insert(0, _STREAMLIT_DIR)

from exposure_intake import parse_exposures  # noqa: E402
from replacement_workbench import (  # noqa: E402
    build_replacement_workbench,
)


FIX_DIR = os.path.join(_HERE, "fixtures")


def _fix(name: str) -> str:
    return os.path.join(FIX_DIR, name)


def _dual_table():
    """Includes both curated-active candidates and a passive sleeve ticker
    PASSV that is also a model holding. The dual-score table uses the
    "scored-universe" name for CAND_FIT (different from the curated name)
    so we can verify the curated name wins."""
    return pd.DataFrame([
        {"Symbol": "LLLA", "Name": "Large Blend Core",
         "Category": "Large Blend", "Fund_Type": "Active",
         "Score_2023_Final": 60.0, "Score_2025_Final": 65.0,
         "Score_Band_2023": "REVIEW", "Score_Band_2025": "REVIEW",
         "Quadrant": "Q4_Mid", "Consensus_Rank": 5,
         "Score_Gap": 5.0, "Rank_2023": 5, "Rank_2025": 5,
         "Action_Flag": "REVIEW", "Primary_Driver": "x"},
        # Note: scored name differs from curated name on purpose — the
        # curated value should win in staff-facing artifacts.
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
        {"Symbol": "CAND_MID", "Name": "Decent-Fit Mid Lean",
         "Category": "Large Blend", "Fund_Type": "Active",
         "Score_2023_Final": 80.0, "Score_2025_Final": 78.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "REVIEW",
         "Quadrant": "Q3_Only_2023", "Consensus_Rank": 2,
         "Score_Gap": -2.0, "Rank_2023": 2, "Rank_2025": 4,
         "Action_Flag": "REVIEW", "Primary_Driver": "w"},
        # Passive sleeve ticker — sits in the scored universe AND in the
        # 100/0 model holdings. Should NOT be recommended as a replacement
        # for an active model holding by default.
        {"Symbol": "PASSV", "Name": "Big Passive Index ETF",
         "Category": "Large Blend", "Fund_Type": "Passive",
         "Score_2023_Final": 99.0, "Score_2025_Final": 99.0,
         "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
         "Quadrant": "Q1_Both_Strong", "Consensus_Rank": 0,
         "Score_Gap": 0.0, "Rank_2023": 0, "Rank_2025": 0,
         "Action_Flag": "LEAD", "Primary_Driver": "passive"},
    ])


def _holdings_with_passive():
    """A 100/0 model that already holds LLLA (the active large-blend slot)
    AND PASSV (the passive large-cap-blend sleeve)."""
    return pd.DataFrame([
        {"Model_Name": "100/0", "Symbol": "LLLA", "Target_Weight": 0.18},
        {"Model_Name": "100/0", "Symbol": "PASSV", "Target_Weight": 0.18},
        {"Model_Name": "100/0", "Symbol": "LLLB", "Target_Weight": 0.10},
        {"Model_Name": "100/0", "Symbol": "LLLC", "Target_Weight": 0.10},
        {"Model_Name": "100/0", "Symbol": "LLLD", "Target_Weight": 0.34},
        {"Model_Name": "100/0", "Symbol": "LLLE", "Target_Weight": 0.10},
    ])


def _scorecard_for_passive():
    return pd.DataFrame([
        {"Model_Name": "100/0", "Symbol": s, "Scoring_Symbol": s}
        for s in ("LLLA", "PASSV", "LLLB", "LLLC", "LLLD", "LLLE")
    ])


def _bench_weights():
    return {"LLLA": 0.58, "LLLD": 0.24, "LLLB": 0.06, "LLLC": 0.06, "LLLE": 0.06}


def _curated_candidate_exposures():
    """Simulate the user's curated active mutual-fund / ETF screen — the
    passive PASSV ticker is intentionally NOT in this file."""
    base = parse_exposures(_fix("exposures_candidates_good.csv")).copy()
    # Override the Name column to assert curated names survive.
    base.loc[base["Symbol"] == "CAND_FIT", "Name"] = "Curated Best-Fit Active Fund"
    return base


def test_uploaded_universe_filters_passive_already_held_by_default():
    """SPYM-style test: passive sleeve ticker (PASSV) is held by the 100/0
    model AND scores #1 on FundScore. With a curated candidate_exposures
    file supplied (which does NOT include PASSV) and default settings,
    PASSV must NOT appear in the candidate list or as the recommended
    replacement."""
    result = build_replacement_workbench(
        _dual_table(), "LLLA", top_n=10, alias_map={},
        scorecard=_scorecard_for_passive(),
        model_holdings=_holdings_with_passive(),
        model_exposures=parse_exposures(_fix("exposures_model_good.csv")),
        benchmark_exposures=parse_exposures(_fix("exposures_bench_good.csv")),
        benchmark_weights=_bench_weights(),
        candidate_exposures=_curated_candidate_exposures(),
    )

    cand_syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    assert "PASSV" not in cand_syms, (
        f"Passive already-held ticker should be excluded; got {cand_syms}"
    )
    # Curated universe restricts to CAND_FIT, CAND_DRIFT, CAND_MID.
    assert set(cand_syms).issubset({"CAND_FIT", "CAND_DRIFT", "CAND_MID"})
    assert result.summary["restrict_to_candidate_exposures"] is True
    assert result.summary["exclude_already_held"] is True
    assert result.summary["candidate_universe_size"] == 3
    # Recommendations should not point at the passive sleeve.
    assert result.summary["best_fundscore_candidate"] != "PASSV"
    assert result.summary["best_benchmark_fit_candidate"] != "PASSV"
    # Benchmark-fit candidates list should also be free of PASSV.
    bf = result.benchmark_fit_candidates
    assert "PASSV" not in bf["Candidate_Symbol"].astype(str).str.upper().tolist()


def test_curated_names_win_over_scored_universe_names():
    """When the user uploads a curated candidate file with a Name, that
    name should appear in the staff-facing tables — not the scored-universe
    name — so committee-facing output matches what they typed in."""
    result = build_replacement_workbench(
        _dual_table(), "LLLA", top_n=10, alias_map={},
        scorecard=_scorecard_for_passive(),
        model_holdings=_holdings_with_passive(),
        model_exposures=parse_exposures(_fix("exposures_model_good.csv")),
        benchmark_exposures=parse_exposures(_fix("exposures_bench_good.csv")),
        benchmark_weights=_bench_weights(),
        candidate_exposures=_curated_candidate_exposures(),
    )
    # Curated name wins in the FundScore short list.
    cand_fit_row = result.candidates.loc[
        result.candidates["Symbol"].astype(str).str.upper() == "CAND_FIT"
    ]
    assert not cand_fit_row.empty
    assert (
        cand_fit_row.iloc[0]["Name"] == "Curated Best-Fit Active Fund"
    ), f"Expected curated name; got {cand_fit_row.iloc[0]['Name']!r}"
    # Curated name wins in the benchmark-fit ranking too.
    bf = result.benchmark_fit_candidates
    bf_fit = bf.loc[bf["Candidate_Symbol"].astype(str).str.upper() == "CAND_FIT"]
    assert not bf_fit.empty
    assert bf_fit.iloc[0]["Name"] == "Curated Best-Fit Active Fund"


def test_universe_mode_scored_keeps_legacy_behavior():
    """With candidate_universe_mode='scored' the workbench falls back to
    the full scored universe (PASSV can show up again). This is the
    legacy/diagnostic path."""
    result = build_replacement_workbench(
        _dual_table(), "LLLA", top_n=10, alias_map={},
        scorecard=_scorecard_for_passive(),
        model_holdings=_holdings_with_passive(),
        model_exposures=parse_exposures(_fix("exposures_model_good.csv")),
        benchmark_exposures=parse_exposures(_fix("exposures_bench_good.csv")),
        benchmark_weights=_bench_weights(),
        candidate_exposures=_curated_candidate_exposures(),
        candidate_universe_mode="scored",
        exclude_already_held=False,
    )
    cand_syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    # In scored mode, the full scored universe (incl. PASSV) is fair game.
    assert "PASSV" in cand_syms
    assert result.summary["restrict_to_candidate_exposures"] is False
    assert result.summary["exclude_already_held"] is False


def test_explicit_restrict_flag_overrides_mode():
    """restrict_to_candidate_exposures=True forces uploaded-universe even
    in 'auto' mode."""
    result = build_replacement_workbench(
        _dual_table(), "LLLA", top_n=10, alias_map={},
        scorecard=_scorecard_for_passive(),
        model_holdings=_holdings_with_passive(),
        model_exposures=parse_exposures(_fix("exposures_model_good.csv")),
        benchmark_exposures=parse_exposures(_fix("exposures_bench_good.csv")),
        benchmark_weights=_bench_weights(),
        candidate_exposures=_curated_candidate_exposures(),
        candidate_universe_mode="auto",
        restrict_to_candidate_exposures=True,
        exclude_already_held=True,
    )
    cand_syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    assert set(cand_syms).issubset({"CAND_FIT", "CAND_DRIFT", "CAND_MID"})
    assert result.summary["restrict_to_candidate_exposures"] is True


def test_no_candidate_file_keeps_legacy_default():
    """Without a candidate_exposures file, default behavior remains the
    legacy 'use the scored universe' path so existing callers are
    unaffected."""
    result = build_replacement_workbench(
        _dual_table(), "LLLA", top_n=10, alias_map={},
        scorecard=_scorecard_for_passive(),
    )
    cand_syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    assert "PASSV" in cand_syms  # legacy: not excluded by default
    assert result.summary["restrict_to_candidate_exposures"] is False
    assert result.summary["exclude_already_held"] is False
    assert result.summary["candidate_universe_size"] is None


def test_include_already_held_override_with_candidate_file():
    """exclude_already_held=False with a candidate file keeps already-held
    names that *are* in the curated file, but they should still be flagged
    via Already_Held."""
    cand_with_passive = _curated_candidate_exposures().copy()
    # Insert a PASSV row into the curated file — user explicitly wants it
    # in the candidate universe even though it's already held.
    extra = cand_with_passive.iloc[0:1].copy()
    extra["Symbol"] = "PASSV"
    extra["Name"] = "Curated Passive Override"
    cand_with_passive = pd.concat([cand_with_passive, extra], ignore_index=True)

    result = build_replacement_workbench(
        _dual_table(), "LLLA", top_n=10, alias_map={},
        scorecard=_scorecard_for_passive(),
        model_holdings=_holdings_with_passive(),
        model_exposures=parse_exposures(_fix("exposures_model_good.csv")),
        benchmark_exposures=parse_exposures(_fix("exposures_bench_good.csv")),
        benchmark_weights=_bench_weights(),
        candidate_exposures=cand_with_passive,
        exclude_already_held=False,
    )
    cand_syms = result.candidates["Symbol"].astype(str).str.upper().tolist()
    assert "PASSV" in cand_syms
    passv_row = result.candidates.loc[
        result.candidates["Symbol"].astype(str).str.upper() == "PASSV"
    ].iloc[0]
    assert bool(passv_row["Already_Held"]) is True
    assert "100/0" in str(passv_row["Held_By_Models"])
    # Curated name should still be applied.
    assert passv_row["Name"] == "Curated Passive Override"


def test_brief_calls_out_curated_universe_and_exclusion():
    result = build_replacement_workbench(
        _dual_table(), "LLLA", top_n=10, alias_map={},
        scorecard=_scorecard_for_passive(),
        model_holdings=_holdings_with_passive(),
        model_exposures=parse_exposures(_fix("exposures_model_good.csv")),
        benchmark_exposures=parse_exposures(_fix("exposures_bench_good.csv")),
        benchmark_weights=_bench_weights(),
        candidate_exposures=_curated_candidate_exposures(),
    )
    md = result.brief_markdown
    assert "uploaded curated" in md.lower() or "candidate universe" in md.lower()
    assert "already-held" in md.lower()


def test_uploaded_mode_with_no_candidate_file_returns_empty_short_list():
    """Edge case: explicit 'uploaded' mode without a candidate file means
    'no curated universe was supplied' — short list should be empty rather
    than silently fall back."""
    result = build_replacement_workbench(
        _dual_table(), "LLLA", top_n=10, alias_map={},
        candidate_universe_mode="uploaded",
    )
    assert result.candidates.empty
    assert result.summary["candidate_universe_source"] == "uploaded_empty"
