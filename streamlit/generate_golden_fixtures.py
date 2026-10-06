"""
Generate Golden Fixtures for Cross-Language Parity Testing
===========================================================
Produces deterministic reference JSON fixtures from the authoritative
Python scoring engine and dual_score_table modules.

Consumed by TypeScript Vitest test suite to verify numerical parity
(within 1e-4 tolerance) and exact categorical/rank equality.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from scoring_engine import (
    CSV_COLUMNS,
    PASSIVE_METRICS,
    ACTIVE_METRICS,
    score_funds,
    score_2023_funds,
    get_metric_percentiles,
)
from dual_score_table import build_dual_score_table


def _clean_val(val: Any) -> Any:
    if val is None or pd.isna(val):
        return None
    if isinstance(val, (np.integer, int)):
        return int(val)
    if isinstance(val, (np.floating, float)):
        return round(float(val), 6)
    return str(val)


def _df_to_records(df: pd.DataFrame, cols: List[str]) -> List[Dict[str, Any]]:
    records = []
    for _, row in df.iterrows():
        rec = {}
        for c in cols:
            if c in row:
                rec[c] = _clean_val(row[c])
            else:
                rec[c] = None
        records.append(rec)
    return records


def generate_synthetic_fixtures() -> Dict[str, Any]:
    # 1. Passive Dominator scenario
    top = {
        "Symbol": "TOP", "Name": "Top Passive", "Index Fund": True,
        "Category Name": "Synthetic Passive Cat",
        "Net Expense Ratio": 0.03,
        "Tracking Error (vs Category) (3Y)": 0.05,
        "Tracking Error (vs Category) (5Y)": 0.06,
        "Tracking Error (vs Category) (10Y)": 0.07,
        "R-Squared (vs Category) (5Y)": 0.99,
        "Share Class Assets Under Management": 1000000000.0,
        "Downside (vs Category) (5Y)": 85.0,
        "Downside (vs Category) (10Y)": 88.0,
        "Max Drawdown (5Y)": 12.0,
        "Max Drawdown (10Y)": 15.0,
    }
    bot = {
        "Symbol": "BOT", "Name": "Bottom Passive", "Index Fund": True,
        "Category Name": "Synthetic Passive Cat",
        "Net Expense Ratio": 0.85,
        "Tracking Error (vs Category) (3Y)": 2.50,
        "Tracking Error (vs Category) (5Y)": 2.60,
        "Tracking Error (vs Category) (10Y)": 2.80,
        "R-Squared (vs Category) (5Y)": 0.65,
        "Share Class Assets Under Management": 50000000.0,
        "Downside (vs Category) (5Y)": 115.0,
        "Downside (vs Category) (10Y)": 120.0,
        "Max Drawdown (5Y)": 25.0,
        "Max Drawdown (10Y)": 30.0,
    }
    df_passive = pd.DataFrame([top, bot])
    scored_passive = score_funds(df_passive)

    # 2. Singleton Category scenario
    single = {
        "Symbol": "SOLO", "Name": "Solo Active Fund", "Index Fund": False,
        "Category Name": "Solo Peer Category",
        "Net Expense Ratio": 0.50,
        "Information Ratio (vs Category) (3Y)": 0.5,
        "Information Ratio (vs Category) (5Y)": 0.6,
        "Information Ratio (vs Category) (10Y)": 0.7,
        "Historical Sortino (3Y)": 1.2,
        "Historical Sortino (5Y)": 1.1,
        "Historical Sortino (10Y)": 1.0,
        "Max Drawdown (5Y)": 18.0,
        "Max Drawdown (10Y)": 20.0,
        "Downside (vs Category) (5Y)": 95.0,
        "Downside (vs Category) (10Y)": 98.0,
        "3 Year Total Returns (Daily)": 0.12,
        "5 Year Total Returns (Daily)": 0.10,
        "10 Year Total Returns (Daily)": 0.09,
        "Upside (vs Category) (5Y)": 105.0,
        "Upside (vs Category) (10Y)": 102.0,
    }
    df_single = pd.DataFrame([single])
    scored_single = score_funds(df_single)

    return {
        "passive_dominator": {
            "inputs": [top, bot],
            "outputs": _df_to_records(scored_passive, [
                "Symbol", "Score_Passive", "Score_Active", "Score_Final", "Score_Band"
            ]),
        },
        "singleton_category": {
            "inputs": [single],
            "outputs": _df_to_records(scored_single, [
                "Symbol", "Score_Passive", "Score_Active", "Score_Final", "Score_Band"
            ]),
        },
    }


def generate_all_fixtures() -> Dict[str, Any]:
    fixtures_dir = os.path.join(_HERE, "tests", "fixtures")
    p25 = os.path.join(fixtures_dir, "ycharts_2025_good.csv")
    p23 = os.path.join(fixtures_dir, "ycharts_2023_good.csv")

    df_2025 = pd.read_csv(p25)
    scored_2025 = score_funds(df_2025)

    df_2023 = pd.read_csv(p23)
    scored_2023 = score_2023_funds(df_2023)

    dual_table = build_dual_score_table(
        df_2025=None, df_2023=None,
        path_2025=p25, path_2023=p23,
        how="inner",
    )

    cols_2025 = [
        "Symbol", "Name", "Category Name", "Index Fund", "Fund_Type",
        "Score_Passive", "Score_Active", "Score_Final", "Score_Band"
    ]
    cols_2023 = [
        "Symbol", "Name", "Category Name", "Score_2023", "Avail_Weight"
    ]
    cols_dual = [
        "Symbol", "Name", "Category", "Fund_Type",
        "Score_2023_Final", "Score_2025_Final", "Score_Gap",
        "Rank_2023", "Rank_2025", "Consensus_Rank",
        "Score_Band_2023", "Score_Band_2025",
        "Quadrant", "Action_Flag", "Primary_Driver",
        "Data_Coverage_2023", "Data_Coverage_2025",
    ]

    return {
        "synthetic": generate_synthetic_fixtures(),
        "fixture_2025_scored": _df_to_records(scored_2025, cols_2025),
        "fixture_2023_scored": _df_to_records(scored_2023, cols_2023),
        "dual_score_table": _df_to_records(dual_table, cols_dual),
    }


def main():
    out_path = os.path.join(_HERE, "golden_scoring_fixtures.json")
    # Also write a copy to webapp/server for direct TS test consumption
    webapp_out_path = os.path.abspath(
        os.path.join(_HERE, "..", "webapp", "server", "golden_scoring_fixtures.json")
    )

    data = generate_all_fixtures()

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote golden fixtures to {out_path}")

    os.makedirs(os.path.dirname(webapp_out_path), exist_ok=True)
    with open(webapp_out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote golden fixtures to {webapp_out_path}")


if __name__ == "__main__":
    main()
