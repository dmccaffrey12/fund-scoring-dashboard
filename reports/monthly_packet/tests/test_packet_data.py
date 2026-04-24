"""
Smoke tests for reports/monthly_packet/packet_data.py.

Builds a synthetic run archive (with optional comparison bundle) in a
temporary directory, then exercises:

  - resolve_run_path() — explicit path / run_date / manifest / newest-dated
  - load_packet_inputs() — happy path, missing optional files, errors
  - derived views — top_by_score / top_by_consensus / disagreement_list /
    dual_lens_matrix / quadrant_counts / metadata_banner

No Quarto is required — this validates the data-loading substrate only.

Run with either:
    pytest reports/monthly_packet/tests/test_packet_data.py
    python reports/monthly_packet/tests/test_packet_data.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _PKT_DIR not in sys.path:
    sys.path.insert(0, _PKT_DIR)

from packet_data import (  # noqa: E402
    load_packet_inputs,
    resolve_run_path,
    top_by_score,
    top_by_consensus,
    disagreement_list,
    dual_lens_matrix,
    quadrant_counts,
    metadata_banner,
    model_stackup,
    action_flag_weight_matrix,
    weak_holdings,
    replacement_candidates_for_committee,
    research_candidates_for_committee,
    alias_notes,
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _make_dual_score_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Symbol": "AAA", "Name": "Alpha Fund", "Category": "Large Growth", "Fund_Type": "Active",
                "Score_2023_Final": 90.0, "Score_2025_Final": 92.0, "Score_Gap": 2.0,
                "Rank_2023": 1, "Rank_2025": 1, "Consensus_Rank": 1,
                "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG", "Quadrant": "Q1_Both_Strong",
                "Data_Coverage_2023": 0.9, "Data_Coverage_2025": 0.95,
                "Primary_Driver": "Stable", "Action_Flag": "LEAD",
            },
            {
                "Symbol": "BBB", "Name": "Beta Fund", "Category": "Large Value", "Fund_Type": "Passive",
                "Score_2023_Final": 45.0, "Score_2025_Final": 85.0, "Score_Gap": 40.0,
                "Rank_2023": 3, "Rank_2025": 2, "Consensus_Rank": 2,
                "Score_Band_2023": "WEAK", "Score_Band_2025": "STRONG", "Quadrant": "Q2_Only_2025",
                "Data_Coverage_2023": 0.7, "Data_Coverage_2025": 0.95,
                "Primary_Driver": "Upgraded by 2025 system", "Action_Flag": "REVIEW",
            },
            {
                "Symbol": "CCC", "Name": "Gamma Fund", "Category": "Mid Blend", "Fund_Type": "Active",
                "Score_2023_Final": 70.0, "Score_2025_Final": 30.0, "Score_Gap": -40.0,
                "Rank_2023": 2, "Rank_2025": 3, "Consensus_Rank": 3,
                "Score_Band_2023": "REVIEW", "Score_Band_2025": "WEAK", "Quadrant": "Q3_Only_2023",
                "Data_Coverage_2023": 0.8, "Data_Coverage_2025": 0.6,
                "Primary_Driver": "Downgraded by 2025 system", "Action_Flag": "WATCH",
            },
        ]
    )


def _make_overlay_fixtures():
    """Return (summary_df, scorecard_df, current_review_df, replacement_df, research_df, metadata)."""
    scorecard = pd.DataFrame([
        {
            "Model_Name": "Conservative", "Symbol": "AAA", "Scoring_Symbol": "AAA",
            "Alias_Applied": False, "Fund_Name": "Alpha", "Target_Weight": 0.5,
            "Target_Weight_Pct": 50.0,
            "Name": "Alpha Fund", "Category": "Large Growth", "Fund_Type": "Active",
            "Score_2023_Final": 90.0, "Score_2025_Final": 92.0, "Score_Gap": 2.0,
            "Rank_2023": 1, "Rank_2025": 1, "Consensus_Rank": 1,
            "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
            "Quadrant": "Q1_Both_Strong", "Primary_Driver": "Stable",
            "Scored_In_Universe": True, "Overlay_Action": "High_Conviction_Hold",
        },
        {
            "Model_Name": "Conservative", "Symbol": "PRBLX", "Scoring_Symbol": "PRILX",
            "Alias_Applied": True, "Fund_Name": "Parnassus", "Target_Weight": 0.3,
            "Target_Weight_Pct": 30.0,
            "Name": "Parnassus Core", "Category": "Large Blend", "Fund_Type": "Active",
            "Score_2023_Final": 40.0, "Score_2025_Final": 45.0, "Score_Gap": 5.0,
            "Rank_2023": 50, "Rank_2025": 45, "Consensus_Rank": 48,
            "Score_Band_2023": "WEAK", "Score_Band_2025": "WEAK",
            "Quadrant": "Q4_Both_Weak", "Primary_Driver": "Weak",
            "Scored_In_Universe": True, "Overlay_Action": "Replacement_Candidate",
        },
        {
            "Model_Name": "Aggressive", "Symbol": "BBB", "Scoring_Symbol": "BBB",
            "Alias_Applied": False, "Fund_Name": "Beta", "Target_Weight": 1.0,
            "Target_Weight_Pct": 100.0,
            "Name": "Beta Fund", "Category": "Large Value", "Fund_Type": "Passive",
            "Score_2023_Final": 85.0, "Score_2025_Final": 55.0, "Score_Gap": -30.0,
            "Rank_2023": 3, "Rank_2025": 30, "Consensus_Rank": 10,
            "Score_Band_2023": "STRONG", "Score_Band_2025": "WEAK",
            "Quadrant": "Q3_Only_2023", "Primary_Driver": "Downgraded",
            "Scored_In_Universe": True, "Overlay_Action": "Performance_Led_Hold_Review_Quality",
        },
    ])
    summary = pd.DataFrame([
        {
            "Model_Name": "Aggressive",
            "Holding_Count": 1, "Total_Target_Weight_Pct": 100.0,
            "Scored_Holding_Count": 1, "Scored_Weight_Pct": 100.0,
            "Weighted_Score_2023": 85.0, "Weighted_Score_2025": 55.0,
            "Weight_Pct_Q1_Both_Strong": 0.0, "Weight_Pct_Q2_Only_2025": 0.0,
            "Weight_Pct_Q3_Only_2023": 100.0, "Weight_Pct_Q4_Both_Weak": 0.0,
            "Weight_Pct_Band_STRONG_2023": 100.0, "Weight_Pct_Band_STRONG_2025": 0.0,
            "Weight_Pct_Band_WEAK_2023": 0.0, "Weight_Pct_Band_WEAK_2025": 100.0,
            "Weight_Pct_HighConviction": 0.0, "Weight_Pct_Replacement": 0.0,
            "Weight_Pct_PerfLed": 100.0, "Weight_Pct_QualityLed": 0.0,
            "Weight_Pct_Unscored": 0.0,
        },
        {
            "Model_Name": "Conservative",
            "Holding_Count": 2, "Total_Target_Weight_Pct": 80.0,
            "Scored_Holding_Count": 2, "Scored_Weight_Pct": 80.0,
            "Weighted_Score_2023": 71.25, "Weighted_Score_2025": 74.375,
            "Weight_Pct_Q1_Both_Strong": 62.5, "Weight_Pct_Q2_Only_2025": 0.0,
            "Weight_Pct_Q3_Only_2023": 0.0, "Weight_Pct_Q4_Both_Weak": 37.5,
            "Weight_Pct_Band_STRONG_2023": 62.5, "Weight_Pct_Band_STRONG_2025": 62.5,
            "Weight_Pct_Band_WEAK_2023": 37.5, "Weight_Pct_Band_WEAK_2025": 37.5,
            "Weight_Pct_HighConviction": 62.5, "Weight_Pct_Replacement": 37.5,
            "Weight_Pct_PerfLed": 0.0, "Weight_Pct_QualityLed": 0.0,
            "Weight_Pct_Unscored": 0.0,
        },
    ])
    current_review = scorecard[
        scorecard["Overlay_Action"].isin([
            "Replacement_Candidate",
            "Performance_Led_Hold_Review_Quality",
        ])
    ].copy().reset_index(drop=True)
    replacement = pd.DataFrame([
        {
            "Model_Name": "Conservative",
            "Current_Symbol": "PRBLX", "Current_Scoring_Symbol": "PRILX",
            "Current_Name": "Parnassus Core", "Current_Category": "Large Blend",
            "Current_Score_2023_Final": 40.0, "Current_Score_2025_Final": 45.0,
            "Current_Score_Band_2023": "WEAK", "Current_Score_Band_2025": "WEAK",
            "Candidate_Rank": 1, "Candidate_Symbol": "ZZZ",
            "Candidate_Name": "Zeta Fund", "Candidate_Category": "Large Blend",
            "Candidate_Fund_Type": "Active",
            "Candidate_Score_2023_Final": 88.0, "Candidate_Score_2025_Final": 90.0,
            "Candidate_Consensus_Rank": 2,
            "Candidate_Score_Band_2023": "STRONG", "Candidate_Score_Band_2025": "STRONG",
            "Candidate_Quadrant": "Q1_Both_Strong",
        },
    ])
    research = pd.DataFrame([
        {
            "Symbol": "RES1", "Name": "Research One", "Category": "Mid Growth",
            "Fund_Type": "Active",
            "Score_2023_Final": 88.0, "Score_2025_Final": 85.0,
            "Rank_2023": 4, "Rank_2025": 6, "Consensus_Rank": 5,
            "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
            "Quadrant": "Q1_Both_Strong", "Primary_Driver": "Consistent",
        },
    ])
    metadata = {
        "model_count": 2,
        "holding_row_count": 3,
        "scored_holding_count": 3,
        "replacement_row_count": 1,
        "research_candidate_count": 1,
        "current_review_count": 2,
        "universe_row_count": 3,
        "alias_applied_rows": 1,
        "distinct_aliases_used": 1,
        "alias_pairs": [{"original": "PRBLX", "scoring": "PRILX"}],
        "action_flag_counts": {
            "High_Conviction_Hold": 1,
            "Replacement_Candidate": 1,
            "Performance_Led_Hold_Review_Quality": 1,
        },
    }
    return summary, scorecard, current_review, replacement, research, metadata


def _write_overlay(run_dir: str):
    summary, scorecard, current_review, replacement, research, metadata = _make_overlay_fixtures()
    out_dir = os.path.join(run_dir, "model_holdings")
    os.makedirs(out_dir, exist_ok=True)
    summary.to_csv(os.path.join(out_dir, "model_summary.csv"), index=False)
    scorecard.to_csv(os.path.join(out_dir, "model_holdings_scorecard.csv"), index=False)
    current_review.to_csv(os.path.join(out_dir, "current_holdings_review.csv"), index=False)
    replacement.to_csv(os.path.join(out_dir, "replacement_candidates.csv"), index=False)
    research.to_csv(os.path.join(out_dir, "research_candidates.csv"), index=False)
    with open(os.path.join(out_dir, "overlay_metadata.json"), "w") as f:
        json.dump(metadata, f)
    return out_dir


def _write_run(
    runs_dir: str,
    run_date: str,
    table: pd.DataFrame,
    with_validation: bool = True,
    with_intake: bool = False,
    comparison: dict | None = None,
    with_overlay: bool = False,
) -> str:
    target = os.path.join(runs_dir, run_date)
    for sub in ("data", "metadata", "validation"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)

    table.to_csv(os.path.join(target, "data", "dual_score_table.csv"), index=False)
    with open(os.path.join(target, "metadata", "run_metadata.json"), "w") as f:
        json.dump(
            {
                "run_date": run_date,
                "generated_at": "2026-04-22T00:00:00+00:00",
                "score_system": "dual-test",
                "inputs": {
                    "path_2025": {"basename": "p25.csv"},
                    "path_2023": {"basename": "p23.csv"},
                },
                "notes": f"fixture {run_date}",
            },
            f,
        )
    if with_validation:
        with open(os.path.join(target, "validation", "validation_report.json"), "w") as f:
            json.dump(
                {
                    "row_count": len(table),
                    "joined_count": int(
                        table[["Score_2023_Final", "Score_2025_Final"]].notna().all(axis=1).sum()
                    ),
                    "band_counts_2025": table["Score_Band_2025"].value_counts().to_dict(),
                    "band_counts_2023": table["Score_Band_2023"].value_counts().to_dict(),
                    "score_2025": {"min": 30.0, "max": 92.0, "mean": 69.0, "missing": 0},
                    "score_2023": {"min": 45.0, "max": 90.0, "mean": 68.3, "missing": 0},
                    "score_gap": {"min": -40.0, "max": 40.0, "mean": 0.7, "missing": 0},
                    "coverage_2025": {"min": 0.6, "mean": 0.83, "missing": 0},
                    "coverage_2023": {"min": 0.7, "mean": 0.8, "missing": 0},
                },
                f,
            )
    if with_intake:
        with open(os.path.join(target, "validation", "intake_report.json"), "w") as f:
            json.dump(
                {
                    "failed": False,
                    "finding_counts": {"error": 0, "warning": 1, "info": 1},
                    "report_2025": {
                        "findings": [
                            {"code": "row_count", "message": "3 rows", "severity": "info"}
                        ]
                    },
                    "report_2023": {"findings": []},
                    "join_findings": [
                        {"code": "join_summary", "message": "all symbols matched", "severity": "warning"}
                    ],
                },
                f,
            )
    if comparison is not None:
        prior_date = comparison["prior_date"]
        comp_dir = os.path.join(target, "comparison", f"prior_{prior_date}")
        os.makedirs(comp_dir, exist_ok=True)
        with open(os.path.join(comp_dir, "summary.json"), "w") as f:
            json.dump(
                {
                    "latest_run_date": run_date,
                    "prior_run_date": prior_date,
                    "latest_row_count": len(table),
                    "prior_row_count": len(table),
                    "new_fund_count": 1,
                    "removed_fund_count": 0,
                    "quadrant_change_count": 1,
                    "action_flag_change_count": 0,
                    "score_mover_count_by_metric": {"Score_2025_Final": 1},
                    "band_change_count_by_column": {"Score_Band_2025": 1},
                },
                f,
            )
        for name in (
            "score_movers.csv",
            "band_changes.csv",
            "quadrant_changes.csv",
            "action_flag_changes.csv",
            "new_funds.csv",
            "removed_funds.csv",
        ):
            pd.DataFrame({"Symbol": ["AAA"], "col": [1]}).to_csv(
                os.path.join(comp_dir, name), index=False
            )

    if with_overlay:
        _write_overlay(target)

    with open(os.path.join(runs_dir, "latest.json"), "w") as f:
        json.dump({"run_date": run_date, "relative_path": run_date}, f)

    return target


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_resolve_via_manifest_and_latest_by_name():
    with tempfile.TemporaryDirectory() as td:
        runs_dir = os.path.join(td, "runs")
        os.makedirs(runs_dir)
        _write_run(runs_dir, "2026-03-22", _make_dual_score_table())
        _write_run(runs_dir, "2026-04-22", _make_dual_score_table())

        hit = resolve_run_path(runs_dir=runs_dir)
        assert os.path.basename(hit) == "2026-04-22", hit

        os.remove(os.path.join(runs_dir, "latest.json"))
        hit2 = resolve_run_path(runs_dir=runs_dir)
        assert os.path.basename(hit2) == "2026-04-22", hit2


def test_resolve_via_run_date_and_run_path():
    with tempfile.TemporaryDirectory() as td:
        runs_dir = os.path.join(td, "runs")
        os.makedirs(runs_dir)
        path = _write_run(runs_dir, "2026-04-22", _make_dual_score_table())

        assert resolve_run_path(run_date="2026-04-22", runs_dir=runs_dir) == path
        assert resolve_run_path(run_path=path) == path
        assert resolve_run_path(run_date="2099-01-01", runs_dir=runs_dir) is None


def test_load_happy_path_with_comparison():
    with tempfile.TemporaryDirectory() as td:
        runs_dir = os.path.join(td, "runs")
        os.makedirs(runs_dir)
        _write_run(runs_dir, "2026-03-22", _make_dual_score_table())
        _write_run(
            runs_dir,
            "2026-04-22",
            _make_dual_score_table(),
            with_intake=True,
            comparison={"prior_date": "2026-03-22"},
        )

        inp = load_packet_inputs(runs_dir=runs_dir)
        assert inp.run_date == "2026-04-22"
        assert len(inp.dual_score_table) == 3
        assert inp.validation is not None
        assert inp.intake is not None
        assert inp.has_comparison
        assert inp.comparison.latest_date == "2026-04-22"
        assert inp.comparison.prior_date == "2026-03-22"
        assert not inp.comparison.score_movers.empty


def test_load_without_optional_artifacts():
    with tempfile.TemporaryDirectory() as td:
        runs_dir = os.path.join(td, "runs")
        os.makedirs(runs_dir)
        _write_run(runs_dir, "2026-04-22", _make_dual_score_table(), with_validation=False)

        inp = load_packet_inputs(runs_dir=runs_dir)
        assert inp.validation is None
        assert inp.intake is None
        assert not inp.has_comparison
        assert "validation_report.json not found" in inp.warnings


def test_derived_views():
    table = _make_dual_score_table()

    top2 = top_by_consensus(table, top_n=2)
    assert list(top2["Symbol"]) == ["AAA", "BBB"]

    top_25 = top_by_score(table, "Score_2025_Final", top_n=2)
    assert list(top_25["Symbol"]) == ["AAA", "BBB"]

    d = disagreement_list(table, min_gap=10.0)
    assert set(d["Symbol"]) == {"BBB", "CCC"}

    matrix = dual_lens_matrix(table)
    assert matrix.loc["STRONG", "STRONG"] == 1
    assert matrix.loc["STRONG", "WEAK"] == 1
    assert matrix.loc["WEAK", "REVIEW"] == 1

    q = quadrant_counts(table)
    assert q.sum() == 3

    banner = metadata_banner({"run_date": "2026-04-22", "inputs": {"path_2025": {"basename": "p.csv"}}})
    assert banner["run_date"] == "2026-04-22"
    assert banner["input_2025"] == "p.csv"


def test_load_packet_inputs_with_model_overlay():
    with tempfile.TemporaryDirectory() as td:
        runs_dir = os.path.join(td, "runs")
        os.makedirs(runs_dir)
        _write_run(runs_dir, "2026-04-22", _make_dual_score_table(), with_overlay=True)

        inp = load_packet_inputs(runs_dir=runs_dir)
        assert inp.has_model_overlay
        mo = inp.model_overlay
        assert mo is not None
        assert not mo.summary.empty
        assert not mo.scorecard.empty
        assert not mo.current_review.empty
        assert not mo.replacement_candidates.empty
        assert not mo.research_candidates.empty
        # Metadata round-trips.
        assert mo.metadata.get("model_count") == 2
        assert mo.metadata.get("alias_pairs") == [
            {"original": "PRBLX", "scoring": "PRILX"},
        ]


def test_load_packet_inputs_without_model_overlay():
    with tempfile.TemporaryDirectory() as td:
        runs_dir = os.path.join(td, "runs")
        os.makedirs(runs_dir)
        _write_run(runs_dir, "2026-04-22", _make_dual_score_table())

        inp = load_packet_inputs(runs_dir=runs_dir)
        assert not inp.has_model_overlay
        assert inp.model_overlay is None
        assert "no model holdings overlay found" in inp.warnings


def test_overlay_partial_artifacts_are_tolerated():
    """Missing individual overlay CSVs should yield empty frames, not errors."""
    with tempfile.TemporaryDirectory() as td:
        runs_dir = os.path.join(td, "runs")
        os.makedirs(runs_dir)
        target = _write_run(runs_dir, "2026-04-22", _make_dual_score_table(), with_overlay=True)
        # Remove optional overlay files; keep the required scorecard.
        for fname in (
            "research_candidates.csv",
            "replacement_candidates.csv",
            "current_holdings_review.csv",
            "overlay_metadata.json",
        ):
            path = os.path.join(target, "model_holdings", fname)
            if os.path.isfile(path):
                os.remove(path)

        inp = load_packet_inputs(runs_dir=runs_dir)
        assert inp.has_model_overlay
        mo = inp.model_overlay
        assert mo.research_candidates.empty
        assert mo.replacement_candidates.empty
        assert mo.current_review.empty
        assert mo.metadata == {}
        assert not mo.scorecard.empty


def test_overlay_derived_views():
    summary, scorecard, current_review, replacement, research, metadata = _make_overlay_fixtures()

    stack = model_stackup(summary)
    assert not stack.empty
    assert "Weighted_Score_2023" in stack.columns

    matrix = action_flag_weight_matrix(summary)
    assert not matrix.empty
    # Weight shares should sum to ~100 per model.
    for model, row in matrix.iterrows():
        assert abs(row.sum() - 100.0) < 0.01, (model, row.to_dict())

    weak = weak_holdings(current_review, top_n=10)
    assert not weak.empty
    assert set(weak["Overlay_Action"]) <= {
        "Replacement_Candidate", "Performance_Led_Hold_Review_Quality",
    }

    r = replacement_candidates_for_committee(replacement)
    assert not r.empty
    assert list(r["Candidate_Rank"]) == [1]

    research_view = research_candidates_for_committee(research, top_n=5)
    assert not research_view.empty
    assert "Symbol" in research_view.columns

    notes = alias_notes(metadata)
    assert notes and notes[0]["original"] == "PRBLX"
    assert notes[0]["scoring"] == "PRILX"
    # The known-alias reason should be filled in for PRBLX->PRILX.
    assert "Parnassus" in notes[0]["reason"]


def test_overlay_derived_views_empty_safe():
    """Derived view helpers should return empty frames when inputs are empty."""
    empty = pd.DataFrame()
    assert model_stackup(empty).empty
    assert action_flag_weight_matrix(empty).empty
    assert weak_holdings(empty).empty
    assert replacement_candidates_for_committee(empty).empty
    assert research_candidates_for_committee(empty).empty
    assert alias_notes(None) == []
    assert alias_notes({}) == []


def test_qmd_code_blocks_importable():
    """Smoke test: the qmd should reference only packet_data symbols that exist.

    We parse the .qmd for python code blocks and confirm every `from
    packet_data import ...` line resolves without ImportError.
    """
    qmd_path = os.path.abspath(os.path.join(_PKT_DIR, "monthly_packet.qmd"))
    assert os.path.isfile(qmd_path)
    with open(qmd_path) as f:
        text = f.read()

    # Find all `from packet_data import (...)` blocks, including multi-line.
    import re
    matches = re.findall(
        r"from\s+packet_data\s+import\s*\(([^)]+)\)",
        text,
    )
    matches += re.findall(
        r"from\s+packet_data\s+import\s+([A-Za-z0-9_,\s]+)$",
        text,
        flags=re.MULTILINE,
    )
    assert matches, "expected at least one `from packet_data import ...` in the qmd"

    import packet_data as pd_mod
    missing = []
    for block in matches:
        for raw in block.split(","):
            name = raw.strip().split("#")[0].strip()
            if not name:
                continue
            if not hasattr(pd_mod, name):
                missing.append(name)
    assert not missing, f"qmd imports symbols not in packet_data: {missing}"


def test_theme_assets_present_and_wired_in():
    """The committee packet depends on a custom SCSS theme + companion CSS.

    This test keeps the render contract honest: if either asset goes missing
    or the qmd stops referencing them, the packet falls back to default
    Bootstrap and the committee-memo aesthetic disappears.
    """
    scss_path = os.path.abspath(os.path.join(_PKT_DIR, "fundscore.scss"))
    css_path = os.path.abspath(os.path.join(_PKT_DIR, "fundscore.css"))
    qmd_path = os.path.abspath(os.path.join(_PKT_DIR, "monthly_packet.qmd"))

    assert os.path.isfile(scss_path), "fundscore.scss theme file is missing"
    assert os.path.isfile(css_path), "fundscore.css companion file is missing"

    scss = open(scss_path).read()
    css = open(css_path).read()
    qmd = open(qmd_path).read()

    # SCSS must expose both the defaults and rules layers Quarto expects.
    assert "/*-- scss:defaults --*/" in scss
    assert "/*-- scss:rules --*/" in scss

    # qmd must reference both theme assets so render picks them up.
    assert "fundscore.scss" in qmd, "qmd no longer references fundscore.scss"
    assert "fundscore.css" in qmd, "qmd no longer references fundscore.css"

    # Print/PDF block is a committee requirement — make sure it stays present.
    assert "@media print" in scss, "print/PDF media block missing from theme"


def test_qmd_uses_packet_palette_for_charts():
    """Charts in the packet should pull from the shared PACKET_PALETTE so the
    committee sees consistent colours across figures. Catch future drift by
    ensuring the palette is defined and at least one chart references it.
    """
    qmd_path = os.path.abspath(os.path.join(_PKT_DIR, "monthly_packet.qmd"))
    qmd = open(qmd_path).read()
    assert "PACKET_PALETTE" in qmd, "shared PACKET_PALETTE not declared in qmd"
    assert qmd.count("PACKET_PALETTE[") >= 3, (
        "expected multiple chart references to PACKET_PALETTE — charts may "
        "have reverted to ad-hoc colours"
    )


def test_errors_when_no_run_found():
    with tempfile.TemporaryDirectory() as td:
        try:
            load_packet_inputs(runs_dir=os.path.join(td, "runs"))
        except FileNotFoundError as e:
            assert "Could not resolve" in str(e)
        else:  # pragma: no cover
            raise AssertionError("expected FileNotFoundError")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all():
    tests = [
        test_resolve_via_manifest_and_latest_by_name,
        test_resolve_via_run_date_and_run_path,
        test_load_happy_path_with_comparison,
        test_load_without_optional_artifacts,
        test_derived_views,
        test_load_packet_inputs_with_model_overlay,
        test_load_packet_inputs_without_model_overlay,
        test_overlay_partial_artifacts_are_tolerated,
        test_overlay_derived_views,
        test_overlay_derived_views_empty_safe,
        test_qmd_code_blocks_importable,
        test_theme_assets_present_and_wired_in,
        test_qmd_uses_packet_palette_for_charts,
        test_errors_when_no_run_found,
    ]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\nAll {len(tests)} tests passed.")


if __name__ == "__main__":
    _run_all()
