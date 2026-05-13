"""
Unit tests for streamlit/workflow_ui.py.

The helpers in workflow_ui are deliberately UI-free, so we can exercise them
end-to-end without running Streamlit. We use a synthetic dual-score table
(same shape as the test_run_archive fixture) to drive archive creation,
previews, and the Excel audit export. The upload/intake paths are exercised
against tiny in-memory CSVs.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_STREAMLIT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _STREAMLIT_DIR not in sys.path:
    sys.path.insert(0, _STREAMLIT_DIR)

from run_archive import create_run_archive  # noqa: E402
import workflow_ui  # noqa: E402


def _synthetic_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Symbol": "AAA", "Name": "Alpha", "Category": "Large Growth",
                "Fund_Type": "Passive",
                "Score_2023_Final": 85.0, "Score_2025_Final": 90.0,
                "Score_Gap": 5.0,
                "Rank_2023": 1, "Rank_2025": 1, "Consensus_Rank": 1,
                "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
                "Quadrant": "Q1_Both_Strong",
                "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0,
                "Primary_Driver": "Stable", "Action_Flag": "LEAD",
            },
            {
                "Symbol": "BBB", "Name": "Beta", "Category": "Large Growth",
                "Fund_Type": "Active",
                "Score_2023_Final": 55.0, "Score_2025_Final": 72.0,
                "Score_Gap": 17.0,
                "Rank_2023": 3, "Rank_2025": 2, "Consensus_Rank": 2,
                "Score_Band_2023": "WEAK", "Score_Band_2025": "REVIEW",
                "Quadrant": "Q4_Both_Weak",
                "Data_Coverage_2023": 0.8, "Data_Coverage_2025": 0.9,
                "Primary_Driver": "Upgraded by 2025 system", "Action_Flag": "REVIEW",
            },
            {
                "Symbol": "CCC", "Name": "Gamma", "Category": "Small Blend",
                "Fund_Type": "Active",
                "Score_2023_Final": 75.0, "Score_2025_Final": 40.0,
                "Score_Gap": -35.0,
                "Rank_2023": 2, "Rank_2025": 3, "Consensus_Rank": 3,
                "Score_Band_2023": "REVIEW", "Score_Band_2025": "WEAK",
                "Quadrant": "Q3_Lost_Strength",
                "Data_Coverage_2023": 0.9, "Data_Coverage_2025": 0.7,
                "Primary_Driver": "Downgraded by 2025 system", "Action_Flag": "REVIEW",
            },
        ]
    )


def test_persist_uploads_round_trip():
    p25, p23, tmp = workflow_ui.persist_uploads(
        b"Symbol,Net Expense Ratio\nAAA,0.05\n",
        b"Symbol,Score_2023\nAAA,80\n",
    )
    try:
        assert os.path.isfile(p25)
        assert os.path.isfile(p23)
        with open(p25) as f:
            assert "Symbol" in f.readline()
    finally:
        workflow_ui.cleanup_tmp(tmp)
        assert not os.path.isdir(tmp)


def test_run_intake_returns_summary_text():
    # Use a deliberately malformed 2025 file so the intake fails fast.
    p25, p23, tmp = workflow_ui.persist_uploads(
        b"NotASymbolColumn\nfoo\n",
        b"Symbol,Score_2023\nAAA,80\n",
    )
    try:
        report = workflow_ui.run_intake(p25, p23)
        assert "summary_text" in report
        assert isinstance(report["summary_text"], str)
        assert report["summary_text"]
        # finding_counts should always be present.
        assert "finding_counts" in report
    finally:
        workflow_ui.cleanup_tmp(tmp)


def test_top_previews_shapes():
    table = _synthetic_table()
    previews = workflow_ui.top_previews(table, top_n=2)
    assert set(previews.keys()) == {
        "top_2023", "top_2025", "top_consensus", "disagreement"
    }
    assert len(previews["top_2023"]) == 2
    # Top 2023 should be sorted by Score_2023_Final desc.
    assert previews["top_2023"].iloc[0]["Symbol"] == "AAA"
    assert previews["top_2023"].iloc[1]["Symbol"] == "CCC"
    # Top 2025 should place AAA first, then BBB.
    assert previews["top_2025"].iloc[0]["Symbol"] == "AAA"
    assert previews["top_2025"].iloc[1]["Symbol"] == "BBB"
    # Disagreement should surface the biggest |gap| first (CCC, -35).
    assert previews["disagreement"].iloc[0]["Symbol"] == "CCC"


def test_available_runs_and_latest_via_synthetic_archive():
    table = _synthetic_table()
    with tempfile.TemporaryDirectory() as tmp:
        create_run_archive(run_date="2026-01-15", runs_dir=tmp, table=table)
        create_run_archive(run_date="2026-02-15", runs_dir=tmp, table=table)
        runs = workflow_ui.available_runs(runs_dir=tmp)
        assert runs == ["2026-01-15", "2026-02-15"]
        latest = workflow_ui.load_latest(runs_dir=tmp)
        assert latest is not None
        assert latest["run_date"] == "2026-02-15"


def test_maybe_compare_returns_none_with_one_run():
    table = _synthetic_table()
    with tempfile.TemporaryDirectory() as tmp:
        create_run_archive(run_date="2026-03-15", runs_dir=tmp, table=table)
        assert workflow_ui.maybe_compare(runs_dir=tmp, write=False) is None


def test_maybe_compare_returns_result_with_two_runs():
    table_a = _synthetic_table()
    table_b = _synthetic_table()
    # Nudge one fund's score so the comparison has a non-trivial mover.
    table_b.loc[table_b["Symbol"] == "BBB", "Score_2025_Final"] = 82.0
    table_b.loc[table_b["Symbol"] == "BBB", "Score_Gap"] = (
        82.0 - table_b.loc[table_b["Symbol"] == "BBB", "Score_2023_Final"].iloc[0]
    )
    with tempfile.TemporaryDirectory() as tmp:
        create_run_archive(run_date="2026-03-15", runs_dir=tmp, table=table_a)
        create_run_archive(run_date="2026-04-15", runs_dir=tmp, table=table_b)
        comp = workflow_ui.maybe_compare(runs_dir=tmp, write=True)
        assert comp is not None
        assert comp["latest_date"] == "2026-04-15"
        assert comp["prior_date"] == "2026-03-15"
        assert "tables" in comp and isinstance(comp["tables"], dict)
        assert "summary" in comp


def test_build_audit_workbook_bytes():
    table = _synthetic_table()
    with tempfile.TemporaryDirectory() as tmp:
        create_run_archive(run_date="2026-04-30", runs_dir=tmp, table=table)
        fname, data = workflow_ui.build_audit_workbook_bytes(
            run_date="2026-04-30",
            runs_dir=tmp,
            include_comparison=False,
        )
        assert fname.endswith(".xlsx")
        assert len(data) > 1000
        # XLSX is a ZIP file — bytes start with the PK signature.
        assert data[:2] == b"PK"


def test_find_packet_html_optional():
    # Either the file exists in this repo or it doesn't — both are valid.
    result = workflow_ui.find_packet_html()
    assert result is None or result.endswith(".html")


def test_check_archive_score_bounds_clean_archive_returns_none():
    table = _synthetic_table()
    with tempfile.TemporaryDirectory() as tmp:
        create_run_archive(run_date="2026-04-30", runs_dir=tmp, table=table)
        assert workflow_ui.check_archive_score_bounds(
            "2026-04-30", runs_dir=tmp,
        ) is None


def test_check_archive_score_bounds_stale_archive_returns_message():
    """An archive with scores above 100 must surface a remediation message."""
    table = _synthetic_table()
    table.loc[0, "Score_2025_Final"] = 109.0
    with tempfile.TemporaryDirectory() as tmp:
        create_run_archive(run_date="2026-04-30", runs_dir=tmp, table=table)
        msg = workflow_ui.check_archive_score_bounds(
            "2026-04-30", runs_dir=tmp,
        )
        assert msg is not None
        assert "Score_2025_Final" in msg
        assert "overwrite" in msg.lower()


def test_check_archive_score_bounds_missing_archive_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        assert workflow_ui.check_archive_score_bounds(
            "2099-01-01", runs_dir=tmp,
        ) is None


def test_build_audit_workbook_bytes_refuses_stale_archive():
    """Stale archives (scores >100) must not produce a workbook."""
    from excel_audit_export import StaleScoreArchiveError

    table = _synthetic_table()
    table.loc[0, "Score_2025_Final"] = 111.0
    with tempfile.TemporaryDirectory() as tmp:
        create_run_archive(run_date="2026-04-30", runs_dir=tmp, table=table)
        try:
            workflow_ui.build_audit_workbook_bytes(
                run_date="2026-04-30",
                runs_dir=tmp,
                include_comparison=False,
            )
        except StaleScoreArchiveError:
            pass
        else:
            raise AssertionError("Expected StaleScoreArchiveError, got none")


if __name__ == "__main__":
    # Allow running as a plain script too.
    test_persist_uploads_round_trip()
    test_run_intake_returns_summary_text()
    test_top_previews_shapes()
    test_available_runs_and_latest_via_synthetic_archive()
    test_maybe_compare_returns_none_with_one_run()
    test_maybe_compare_returns_result_with_two_runs()
    test_build_audit_workbook_bytes()
    test_find_packet_html_optional()
    test_check_archive_score_bounds_clean_archive_returns_none()
    test_check_archive_score_bounds_stale_archive_returns_message()
    test_check_archive_score_bounds_missing_archive_returns_none()
    test_build_audit_workbook_bytes_refuses_stale_archive()
    print("ok")
