"""
Smoke tests for the run_comparison module.

Builds two small synthetic dual-score tables, archives them via
run_archive.create_run_archive, then runs compare_runs / run_comparison
and checks that score deltas, band changes, quadrant/action-flag
transitions, and new/removed-fund tables land where we expect.

Run with either:
    pytest streamlit/tests/test_run_comparison.py
    python streamlit/tests/test_run_comparison.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_STREAMLIT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _STREAMLIT_DIR not in sys.path:
    sys.path.insert(0, _STREAMLIT_DIR)

from run_archive import create_run_archive  # noqa: E402
from run_comparison import (  # noqa: E402
    ACTION_FLAG_CHANGES_NAME,
    BAND_CHANGES_NAME,
    InsufficientRunsError,
    NEW_FUNDS_NAME,
    QUADRANT_CHANGES_NAME,
    REMOVED_FUNDS_NAME,
    SCORE_MOVERS_NAME,
    SUMMARY_NAME,
    compare_runs,
    default_comparison_dir,
    resolve_runs,
    run_comparison,
)


def _row(**overrides):
    base = {
        "Symbol": "AAA", "Name": "Alpha", "Category": "Large Growth",
        "Fund_Type": "Passive",
        "Score_2023_Final": 80.0, "Score_2025_Final": 80.0,
        "Score_Gap": 0.0,
        "Rank_2023": 1, "Rank_2025": 1, "Consensus_Rank": 1,
        "Score_Band_2023": "STRONG", "Score_Band_2025": "STRONG",
        "Quadrant": "Q1_Both_Strong",
        "Data_Coverage_2023": 1.0, "Data_Coverage_2025": 1.0,
        "Primary_Driver": "Stable", "Action_Flag": "LEAD",
    }
    base.update(overrides)
    return base


def _prior_table() -> pd.DataFrame:
    return pd.DataFrame([
        _row(Symbol="AAA", Score_2023_Final=85.0, Score_2025_Final=90.0,
             Rank_2023=1, Rank_2025=1, Consensus_Rank=1,
             Score_Band_2023="STRONG", Score_Band_2025="STRONG",
             Quadrant="Q1_Both_Strong", Action_Flag="LEAD"),
        _row(Symbol="BBB", Name="Beta", Fund_Type="Active",
             Score_2023_Final=55.0, Score_2025_Final=58.0,
             Rank_2023=3, Rank_2025=3, Consensus_Rank=3,
             Score_Band_2023="WEAK", Score_Band_2025="WEAK",
             Quadrant="Q4_Both_Weak", Action_Flag="DROP"),
        _row(Symbol="CCC", Name="Charlie",
             Score_2023_Final=72.0, Score_2025_Final=70.0,
             Rank_2023=2, Rank_2025=2, Consensus_Rank=2,
             Score_Band_2023="REVIEW", Score_Band_2025="REVIEW",
             Quadrant="Q4_Both_Weak", Action_Flag="WATCH"),
    ])


def _latest_table() -> pd.DataFrame:
    # AAA: small score drift, same band/quadrant (score mover but no transitions)
    # BBB: big upgrade crossing bands & quadrant
    # CCC: REMOVED (absent)
    # DDD: NEW
    return pd.DataFrame([
        _row(Symbol="AAA", Score_2023_Final=86.0, Score_2025_Final=88.5,
             Rank_2023=1, Rank_2025=1, Consensus_Rank=1,
             Score_Band_2023="STRONG", Score_Band_2025="STRONG",
             Quadrant="Q1_Both_Strong", Action_Flag="LEAD"),
        _row(Symbol="BBB", Name="Beta", Fund_Type="Active",
             Score_2023_Final=82.0, Score_2025_Final=85.0,
             Rank_2023=2, Rank_2025=2, Consensus_Rank=2,
             Score_Band_2023="STRONG", Score_Band_2025="STRONG",
             Quadrant="Q1_Both_Strong", Action_Flag="LEAD"),
        _row(Symbol="DDD", Name="Delta",
             Score_2023_Final=65.0, Score_2025_Final=68.0,
             Rank_2023=3, Rank_2025=3, Consensus_Rank=3,
             Score_Band_2023="REVIEW", Score_Band_2025="REVIEW",
             Quadrant="Q4_Both_Weak", Action_Flag="WATCH"),
    ])


def _archive_pair(tmp: str):
    create_run_archive(run_date="2026-02-15", runs_dir=tmp, table=_prior_table())
    create_run_archive(run_date="2026-03-15", runs_dir=tmp, table=_latest_table())


# ---------------------------------------------------------------------------

def test_compare_runs_identifies_score_movers():
    latest = {"run_date": "2026-03-15", "table": _latest_table()}
    prior = {"run_date": "2026-02-15", "table": _prior_table()}
    result = compare_runs(latest, prior)

    movers = result.score_movers
    # AAA changed 2023 (85->86) and 2025 (90->88.5); BBB moved both big.
    # CCC and DDD are single-sided so excluded from movers.
    symbols = set(movers["Symbol"].unique())
    assert symbols == {"AAA", "BBB"}
    # Largest 2023 mover should be BBB (+27).
    by_metric = movers.groupby("Metric").first().reset_index()
    s23 = by_metric[by_metric["Metric"] == "Score_2023_Final"].iloc[0]
    assert s23["Symbol"] == "BBB"
    assert s23["Delta"] == 27.0


def test_compare_runs_detects_band_and_quadrant_transitions():
    latest = {"run_date": "2026-03-15", "table": _latest_table()}
    prior = {"run_date": "2026-02-15", "table": _prior_table()}
    result = compare_runs(latest, prior)

    band = result.band_changes
    # BBB transitioned WEAK->STRONG on both 2023 and 2025 bands.
    bbb = band[band["Symbol"] == "BBB"]
    assert set(bbb["Column"]) == {"Score_Band_2023", "Score_Band_2025"}
    assert all(bbb["From"] == "WEAK") and all(bbb["To"] == "STRONG")

    quad = result.quadrant_changes
    # Only BBB's quadrant flipped; AAA stayed Q1.
    assert list(quad["Symbol"]) == ["BBB"]
    assert quad.iloc[0]["From"] == "Q4_Both_Weak"
    assert quad.iloc[0]["To"] == "Q1_Both_Strong"

    action = result.action_flag_changes
    assert list(action["Symbol"]) == ["BBB"]
    assert action.iloc[0]["From"] == "DROP"
    assert action.iloc[0]["To"] == "LEAD"


def test_compare_runs_flags_new_and_removed():
    latest = {"run_date": "2026-03-15", "table": _latest_table()}
    prior = {"run_date": "2026-02-15", "table": _prior_table()}
    result = compare_runs(latest, prior)

    assert list(result.new_funds["Symbol"]) == ["DDD"]
    assert list(result.removed_funds["Symbol"]) == ["CCC"]
    # Metadata carried through from the side where the fund exists.
    assert result.new_funds.iloc[0]["Name"] == "Delta"
    assert result.removed_funds.iloc[0]["Name"] == "Charlie"


def test_summary_counts_are_consistent():
    latest = {"run_date": "2026-03-15", "table": _latest_table()}
    prior = {"run_date": "2026-02-15", "table": _prior_table()}
    result = compare_runs(latest, prior)
    s = result.summary

    assert s["latest_run_date"] == "2026-03-15"
    assert s["prior_run_date"] == "2026-02-15"
    assert s["latest_row_count"] == 3
    assert s["prior_row_count"] == 3
    assert s["new_fund_count"] == 1
    assert s["removed_fund_count"] == 1
    assert s["quadrant_change_count"] == 1
    assert s["action_flag_change_count"] == 1
    # 2 band-changed rows, one per column, but only BBB changes.
    assert s["band_change_count_by_column"]["Score_Band_2023"] == 1
    assert s["band_change_count_by_column"]["Score_Band_2025"] == 1


def test_run_comparison_writes_expected_layout():
    with tempfile.TemporaryDirectory() as tmp:
        _archive_pair(tmp)
        result, paths = run_comparison(runs_dir=tmp)
        expected_dir = default_comparison_dir(tmp, "2026-03-15", "2026-02-15")
        for name in (
            SCORE_MOVERS_NAME,
            BAND_CHANGES_NAME,
            QUADRANT_CHANGES_NAME,
            ACTION_FLAG_CHANGES_NAME,
            NEW_FUNDS_NAME,
            REMOVED_FUNDS_NAME,
            SUMMARY_NAME,
        ):
            assert os.path.isfile(os.path.join(expected_dir, name)), name
            assert paths[name] == os.path.join(expected_dir, name)

        with open(os.path.join(expected_dir, SUMMARY_NAME)) as f:
            summary = json.load(f)
        assert summary["latest_run_date"] == "2026-03-15"
        assert summary["new_fund_count"] == 1

        movers = pd.read_csv(os.path.join(expected_dir, SCORE_MOVERS_NAME))
        # BBB's 2023 delta of +27 should appear.
        hit = movers[
            (movers["Symbol"] == "BBB") & (movers["Metric"] == "Score_2023_Final")
        ]
        assert not hit.empty and float(hit.iloc[0]["Delta"]) == 27.0


def test_run_comparison_with_explicit_dates():
    with tempfile.TemporaryDirectory() as tmp:
        create_run_archive(run_date="2026-01-15", runs_dir=tmp, table=_prior_table())
        create_run_archive(run_date="2026-02-15", runs_dir=tmp, table=_latest_table())
        create_run_archive(run_date="2026-03-15", runs_dir=tmp, table=_prior_table())

        result, _ = run_comparison(
            runs_dir=tmp,
            latest_date="2026-02-15",
            prior_date="2026-01-15",
            write=False,
        )
        assert result.latest_date == "2026-02-15"
        assert result.prior_date == "2026-01-15"


def test_insufficient_runs_raises():
    with tempfile.TemporaryDirectory() as tmp:
        create_run_archive(run_date="2026-01-15", runs_dir=tmp, table=_prior_table())
        try:
            run_comparison(runs_dir=tmp, write=False)
        except InsufficientRunsError:
            return
        raise AssertionError("Expected InsufficientRunsError with only one run")


def test_empty_runs_dir_raises():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            resolve_runs(runs_dir=tmp)
        except InsufficientRunsError:
            return
        raise AssertionError("Expected InsufficientRunsError with zero runs")


def test_top_n_movers_caps_per_metric():
    # Five symbols changing 2023 scores by different magnitudes.
    prior = pd.DataFrame([
        _row(Symbol=s, Score_2023_Final=50.0, Score_2025_Final=50.0)
        for s in ["A", "B", "C", "D", "E"]
    ])
    latest = pd.DataFrame([
        _row(Symbol="A", Score_2023_Final=60.0, Score_2025_Final=50.0),  # +10
        _row(Symbol="B", Score_2023_Final=55.0, Score_2025_Final=50.0),  # +5
        _row(Symbol="C", Score_2023_Final=70.0, Score_2025_Final=50.0),  # +20
        _row(Symbol="D", Score_2023_Final=45.0, Score_2025_Final=50.0),  # -5
        _row(Symbol="E", Score_2023_Final=80.0, Score_2025_Final=50.0),  # +30
    ])
    result = compare_runs(
        {"run_date": "b", "table": latest},
        {"run_date": "a", "table": prior},
        top_n_movers=2,
    )
    s23 = result.score_movers[result.score_movers["Metric"] == "Score_2023_Final"]
    # Top 2 by |delta| are E (30) and C (20).
    assert list(s23["Symbol"]) == ["E", "C"]


def test_missing_score_column_handled_gracefully():
    prior = _prior_table().drop(columns=["Consensus_Rank"])
    latest = _latest_table().drop(columns=["Consensus_Rank"])
    result = compare_runs(
        {"run_date": "b", "table": latest},
        {"run_date": "a", "table": prior},
    )
    metrics = set(result.score_movers["Metric"].unique())
    assert "Consensus_Rank" not in metrics
    assert "Score_2023_Final" in metrics


def main() -> int:
    funcs = [
        test_compare_runs_identifies_score_movers,
        test_compare_runs_detects_band_and_quadrant_transitions,
        test_compare_runs_flags_new_and_removed,
        test_summary_counts_are_consistent,
        test_run_comparison_writes_expected_layout,
        test_run_comparison_with_explicit_dates,
        test_insufficient_runs_raises,
        test_empty_runs_dir_raises,
        test_top_n_movers_caps_per_metric,
        test_missing_score_column_handled_gracefully,
    ]
    failed = 0
    for fn in funcs:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(main())
