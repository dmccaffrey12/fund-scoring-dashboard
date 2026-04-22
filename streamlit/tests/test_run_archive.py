"""
Smoke tests for the run_archive module.

Creates a temporary archive directory, writes a couple of dated runs
from a synthetic dual-score table, then checks file layout, metadata
integrity, and the list/load helpers.

Run with either:
    pytest streamlit/tests/test_run_archive.py
    python streamlit/tests/test_run_archive.py
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

from run_archive import (  # noqa: E402
    DUAL_TABLE_NAME,
    LATEST_MANIFEST_NAME,
    METADATA_NAME,
    VALIDATION_NAME,
    build_validation_report,
    create_run_archive,
    list_runs,
    load_latest_run,
    load_prior_run,
    load_run,
)


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
                "Rank_2023": 2, "Rank_2025": 2, "Consensus_Rank": 2,
                "Score_Band_2023": "WEAK", "Score_Band_2025": "REVIEW",
                "Quadrant": "Q4_Both_Weak",
                "Data_Coverage_2023": 0.8, "Data_Coverage_2025": 0.9,
                "Primary_Driver": "Upgraded by 2025 system", "Action_Flag": "REVIEW",
            },
        ]
    )


def test_create_run_archive_writes_expected_files():
    table = _synthetic_table()
    with tempfile.TemporaryDirectory() as tmp:
        target = create_run_archive(
            run_date="2026-01-15", runs_dir=tmp, table=table,
            notes="unit test",
        )
        assert os.path.isdir(target)
        assert os.path.isfile(os.path.join(target, "data", DUAL_TABLE_NAME))
        assert os.path.isfile(os.path.join(target, "metadata", METADATA_NAME))
        assert os.path.isfile(os.path.join(target, "validation", VALIDATION_NAME))
        assert os.path.isfile(os.path.join(tmp, LATEST_MANIFEST_NAME))

        with open(os.path.join(target, "metadata", METADATA_NAME)) as f:
            meta = json.load(f)
        assert meta["run_date"] == "2026-01-15"
        assert meta["notes"] == "unit test"
        assert meta["outputs"]["dual_score_table"]["row_count"] == 2
        assert meta["outputs"]["dual_score_table"]["sha256"]

        with open(os.path.join(target, "validation", VALIDATION_NAME)) as f:
            report = json.load(f)
        assert report["row_count"] == 2
        assert report["joined_count"] == 2
        assert report["band_counts_2025"]["STRONG"] == 1
        assert report["quadrant_counts"]["Q1_Both_Strong"] == 1


def test_duplicate_date_requires_overwrite():
    table = _synthetic_table()
    with tempfile.TemporaryDirectory() as tmp:
        create_run_archive(run_date="2026-02-01", runs_dir=tmp, table=table)
        try:
            create_run_archive(run_date="2026-02-01", runs_dir=tmp, table=table)
        except FileExistsError:
            pass
        else:
            raise AssertionError("Expected FileExistsError on duplicate run date")
        # Succeeds with overwrite=True
        create_run_archive(
            run_date="2026-02-01", runs_dir=tmp, table=table, overwrite=True,
        )


def test_list_and_load_latest_and_prior():
    table = _synthetic_table()
    with tempfile.TemporaryDirectory() as tmp:
        create_run_archive(run_date="2026-01-15", runs_dir=tmp, table=table)
        create_run_archive(run_date="2026-02-15", runs_dir=tmp, table=table)
        create_run_archive(run_date="2026-03-15", runs_dir=tmp, table=table)

        runs = list_runs(tmp)
        assert runs == ["2026-01-15", "2026-02-15", "2026-03-15"]

        latest = load_latest_run(tmp)
        assert latest["run_date"] == "2026-03-15"
        assert isinstance(latest["table"], pd.DataFrame)
        assert len(latest["table"]) == 2

        specific = load_run("2026-02-15", runs_dir=tmp)
        assert specific["metadata"]["run_date"] == "2026-02-15"

        prior = load_prior_run("2026-03-15", runs_dir=tmp)
        assert prior is not None and prior["run_date"] == "2026-02-15"

        earliest_prior = load_prior_run("2026-01-15", runs_dir=tmp)
        assert earliest_prior is None


def test_latest_manifest_fallback_when_missing():
    table = _synthetic_table()
    with tempfile.TemporaryDirectory() as tmp:
        create_run_archive(run_date="2026-01-15", runs_dir=tmp, table=table)
        create_run_archive(run_date="2026-02-15", runs_dir=tmp, table=table)
        os.remove(os.path.join(tmp, LATEST_MANIFEST_NAME))
        latest = load_latest_run(tmp)
        assert latest["run_date"] == "2026-02-15"


def test_validation_report_shape_on_empty_table():
    empty = pd.DataFrame(columns=[
        "Symbol", "Score_2023_Final", "Score_2025_Final", "Score_Gap",
        "Score_Band_2023", "Score_Band_2025", "Quadrant", "Action_Flag",
    ])
    report = build_validation_report(empty)
    assert report["row_count"] == 0
    assert report["joined_count"] == 0
    assert report["band_counts_2025"] == {}
    assert report["quadrant_counts"] == {}


def test_invalid_run_date_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            create_run_archive(run_date="not-a-date", runs_dir=tmp, table=_synthetic_table())
        except ValueError:
            return
        raise AssertionError("Expected ValueError for bad --run-date")


def main() -> int:
    funcs = [
        test_create_run_archive_writes_expected_files,
        test_duplicate_date_requires_overwrite,
        test_list_and_load_latest_and_prior,
        test_latest_manifest_fallback_when_missing,
        test_validation_report_shape_on_empty_table,
        test_invalid_run_date_rejected,
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
