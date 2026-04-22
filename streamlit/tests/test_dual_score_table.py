"""
Smoke tests for the dual_score_table data contract.

Run with either:
    pytest streamlit/tests/test_dual_score_table.py
    python streamlit/tests/test_dual_score_table.py

The module-level `main()` mirrors the pytest assertions so the file is
useful as a standalone smoke check in environments without pytest.
"""

from __future__ import annotations

import os
import sys

import pandas as pd

# Make `streamlit/` importable when running as a bare script.
_HERE = os.path.dirname(os.path.abspath(__file__))
_STREAMLIT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _STREAMLIT_DIR not in sys.path:
    sys.path.insert(0, _STREAMLIT_DIR)

from dual_score_table import (  # noqa: E402
    build_dual_score_table,
    CORE_REQUIRED_COLUMNS,
    VALID_QUADRANTS,
)


def _table():
    # Build once using bundled defaults.
    return build_dual_score_table()


def test_builds_from_bundled_data():
    table = _table()
    assert isinstance(table, pd.DataFrame)
    assert len(table) > 0, "Dual-score table is empty"


def test_required_core_columns_present():
    table = _table()
    missing = [c for c in CORE_REQUIRED_COLUMNS if c not in table.columns]
    assert not missing, f"Missing required columns: {missing}"


def test_ranks_are_populated():
    table = _table()
    for col in ("Rank_2023", "Rank_2025", "Consensus_Rank"):
        # At least 90% of rows should have a rank.
        populated = table[col].notna().mean()
        assert populated >= 0.9, f"{col} only {populated:.1%} populated"


def test_quadrants_are_valid():
    table = _table()
    bad = set(table["Quadrant"].unique()) - VALID_QUADRANTS
    assert not bad, f"Invalid quadrant labels: {bad}"


def test_score_gap_matches_components():
    table = _table()
    diff = (table["Score_2025_Final"] - table["Score_2023_Final"]) - table["Score_Gap"]
    # Floating-point tolerance
    assert diff.abs().max() < 1e-6


def test_fund_type_values():
    table = _table()
    if "Fund_Type" not in table.columns:
        return  # graceful: column was omitted
    allowed = {"Passive", "Active"}
    observed = set(table["Fund_Type"].dropna().unique())
    assert observed.issubset(allowed), f"Unexpected Fund_Type values: {observed - allowed}"


def main() -> int:
    funcs = [
        test_builds_from_bundled_data,
        test_required_core_columns_present,
        test_ranks_are_populated,
        test_quadrants_are_valid,
        test_score_gap_matches_components,
        test_fund_type_values,
    ]
    failed = 0
    for fn in funcs:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(main())
