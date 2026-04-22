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


def _write_run(
    runs_dir: str,
    run_date: str,
    table: pd.DataFrame,
    with_validation: bool = True,
    with_intake: bool = False,
    comparison: dict | None = None,
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
        test_errors_when_no_run_found,
    ]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\nAll {len(tests)} tests passed.")


if __name__ == "__main__":
    _run_all()
