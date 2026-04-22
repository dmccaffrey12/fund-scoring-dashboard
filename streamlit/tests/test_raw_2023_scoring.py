"""
Tests for computing Score_2023 directly from a raw YCharts 2023 export.

Covers:
- ``score_2023_funds`` produces a 0-100 score and Avail_Weight column.
- ``has_raw_2023_metrics`` detects raw-vs-prescored inputs.
- ``build_dual_score_table`` falls back to raw scoring when the 2023 side
  lacks ``Score_2023``.

Run:
    pytest streamlit/tests/test_raw_2023_scoring.py
    python streamlit/tests/test_raw_2023_scoring.py
"""

from __future__ import annotations

import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_STREAMLIT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _STREAMLIT_DIR not in sys.path:
    sys.path.insert(0, _STREAMLIT_DIR)

from scoring_engine import (  # noqa: E402
    SYSTEM_2023_METRICS,
    SYSTEM_2023_TOTAL_WEIGHT,
    has_raw_2023_metrics,
    score_2023_funds,
)
from dual_score_table import build_dual_score_table  # noqa: E402

FIXTURE_2023 = os.path.join(_HERE, "fixtures", "ycharts_2023_good.csv")
FIXTURE_2025 = os.path.join(_HERE, "fixtures", "ycharts_2025_good.csv")


def _load_raw_2023() -> pd.DataFrame:
    return pd.read_csv(FIXTURE_2023)


def test_total_weight_is_100():
    assert SYSTEM_2023_TOTAL_WEIGHT == 100, (
        f"SYSTEM_2023_METRICS must sum to 100, got {SYSTEM_2023_TOTAL_WEIGHT}"
    )


def test_has_raw_2023_metrics_on_raw_export():
    df = _load_raw_2023()
    assert has_raw_2023_metrics(df) is True


def test_has_raw_2023_metrics_false_on_prescored_csv():
    # A minimal prescored frame: category present but no metric columns.
    df = pd.DataFrame({
        "Symbol": ["AAA"],
        "Category Name": ["Fake Cat"],
        "Score_2023": [75.0],
    })
    assert has_raw_2023_metrics(df) is False


def test_score_2023_funds_adds_score_and_avail_weight():
    df = _load_raw_2023()
    scored = score_2023_funds(df)
    assert "Score_2023" in scored.columns
    assert "Avail_Weight" in scored.columns
    # Scores must be within [0, 100] (inclusive) where present.
    scores = scored["Score_2023"].dropna()
    assert len(scores) > 0, "No scores were produced"
    assert scores.min() >= 0.0
    assert scores.max() <= 100.0
    # Avail_Weight is expressed on a 0-100 scale.
    aw = scored["Avail_Weight"].dropna()
    assert aw.min() >= 0.0
    assert aw.max() <= 100.0


def test_score_2023_funds_respects_missing_columns():
    df = _load_raw_2023()
    # Drop a couple of metric columns and confirm scores still compute but
    # Avail_Weight drops below 100 for the affected rows.
    dropped = df.drop(columns=["Alpha (vs Category) (5Y)"])
    scored = score_2023_funds(dropped)
    # 11 points removed (Alpha 5Y weight) → Avail_Weight should cap at 89.
    assert scored["Avail_Weight"].max() <= 89.0 + 1e-6


def test_build_dual_score_table_computes_score_2023_from_raw():
    df_2023 = _load_raw_2023()
    assert "Score_2023" not in df_2023.columns

    table = build_dual_score_table(
        df_2023=df_2023,
        path_2025=FIXTURE_2025,
        how="inner",
    )

    assert len(table) > 0
    assert "Score_2023_Final" in table.columns
    # At least one row should have a finite 2023 score.
    assert table["Score_2023_Final"].notna().any()


def main() -> int:
    funcs = [
        test_total_weight_is_100,
        test_has_raw_2023_metrics_on_raw_export,
        test_has_raw_2023_metrics_false_on_prescored_csv,
        test_score_2023_funds_adds_score_and_avail_weight,
        test_score_2023_funds_respects_missing_columns,
        test_build_dual_score_table_computes_score_2023_from_raw,
    ]
    failed = 0
    for fn in funcs:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:  # pragma: no cover
            failed += 1
            print(f"ERROR {fn.__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(main())
