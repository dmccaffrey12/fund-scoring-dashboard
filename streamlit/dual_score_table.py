"""
Dual-Score Table
================
Canonical one-row-per-fund join between the 2023 Combined System scores and
the 2025 Split System (Passive/Active) scores.

This is the shared data contract consumed by:
    - Streamlit app  (Fund Comparison / Dual-Lens Matrix views)
    - Quarto monthly packet
    - Future Excel audit export

Single entry point: `build_dual_score_table(...)`.

Columns produced (columns omitted gracefully if source data is missing):

    Symbol                  str   — ticker (join key)
    Name                    str   — fund name (prefers 2025 source)
    Category                str   — Morningstar category (prefers 2025 source)
    Fund_Type               str   — Passive | Active (from 2025 engine)
    Score_2023_Final        float — 2023 Combined System score (0-100)
    Score_2025_Final        float — 2025 system score (0-100)
    Score_Gap               float — Score_2025_Final - Score_2023_Final
    Rank_2023               int   — dense rank on Score_2023_Final (1 = best)
    Rank_2025               int   — dense rank on Score_2025_Final (1 = best)
    Consensus_Rank          int   — rank on the average of the two rank cols
    Score_Band_2023         str   — STRONG | REVIEW | WEAK
    Score_Band_2025         str   — STRONG | REVIEW | WEAK
    Quadrant                str   — Q1_Both_Strong | Q2_Only_2025 |
                                    Q3_Only_2023 | Q4_Both_Weak
    Data_Coverage_2023      float — 0.0-1.0 (from Avail_Weight / 100)
    Data_Coverage_2025      float — 0.0-1.0 (share of 2025 metric weight
                                    actually available for the fund)
    Primary_Driver          str   — rough heuristic on Score_Gap direction
    Action_Flag             str   — LEAD | REVIEW | WATCH | DROP

Quadrant thresholds follow the Score_Band thresholds (80 / 60).
"""

from __future__ import annotations

import argparse
import os
from typing import Optional

import numpy as np
import pandas as pd

from scoring_engine import (
    CSV_COLUMNS,
    PASSIVE_METRICS,
    ACTIVE_METRICS,
    PASSIVE_RESCALE,
    load_and_score,
    get_score_band,
)


# ---------------------------------------------------------------------------
# Defaults — bundled sample/legacy files
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_2025_PATH = os.path.join(_HERE, "sample_data.csv")
DEFAULT_2023_PATH = os.path.join(_HERE, "scores_2023.csv")
DEFAULT_OUTPUT_PATH = os.path.join(_HERE, "outputs", "dual_score_table.csv")

CORE_REQUIRED_COLUMNS = [
    "Symbol",
    "Score_2023_Final",
    "Score_2025_Final",
    "Score_Gap",
    "Rank_2023",
    "Rank_2025",
    "Consensus_Rank",
    "Score_Band_2023",
    "Score_Band_2025",
    "Quadrant",
]

VALID_QUADRANTS = {"Q1_Both_Strong", "Q2_Only_2025", "Q3_Only_2023", "Q4_Both_Weak"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_2025_coverage(df: pd.DataFrame) -> pd.Series:
    """
    For each 2025 fund compute the share of its system's total metric weight
    that is backed by a non-null raw value. Returns a float 0.0-1.0.

    Funds are scored by either the Passive or Active metric set depending on
    Fund_Type; the denominator is therefore that set's total weight.
    """
    if "Fund_Type" not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)

    passive_total = sum(w for _, w, _ in PASSIVE_METRICS)
    active_total = sum(w for _, w, _ in ACTIVE_METRICS)

    coverage = pd.Series(0.0, index=df.index, dtype=float)

    for metrics_set, total, mask in (
        (PASSIVE_METRICS, passive_total, df["Fund_Type"] == "Passive"),
        (ACTIVE_METRICS, active_total, df["Fund_Type"] == "Active"),
    ):
        if not mask.any():
            continue
        sub = df.loc[mask]
        avail = pd.Series(0.0, index=sub.index, dtype=float)
        for key, weight, _direction in metrics_set:
            col = CSV_COLUMNS.get(key, key)
            if col in sub.columns:
                avail += sub[col].notna().astype(float) * weight
        coverage.loc[mask] = avail / total

    # Funds with neither Passive nor Active label: NaN
    unknown = ~df["Fund_Type"].isin(["Passive", "Active"])
    coverage.loc[unknown] = np.nan
    return coverage


def _classify_quadrant(score_2023: float, score_2025: float) -> str:
    """Assign a dual-lens quadrant label using the STRONG threshold (>= 80)."""
    if pd.isna(score_2023) or pd.isna(score_2025):
        return "Q4_Both_Weak"  # conservative fallback
    strong_2023 = score_2023 >= 80
    strong_2025 = score_2025 >= 80
    if strong_2023 and strong_2025:
        return "Q1_Both_Strong"
    if strong_2025 and not strong_2023:
        return "Q2_Only_2025"
    if strong_2023 and not strong_2025:
        return "Q3_Only_2023"
    return "Q4_Both_Weak"


def _primary_driver(row: pd.Series) -> str:
    """Heuristic label for what moved the score between systems."""
    gap = row.get("Score_Gap")
    if pd.isna(gap):
        return "UNKNOWN"
    if gap >= 10:
        return "Upgraded by 2025 system"
    if gap <= -10:
        return "Downgraded by 2025 system"
    return "Stable"


def _action_flag(row: pd.Series) -> str:
    """
    Coarse action flag for committee triage:

        LEAD   — Both systems rate the fund STRONG (Q1).
        REVIEW — One system STRONG (Q2 or Q3).
        WATCH  — Both REVIEW band or borderline.
        DROP   — Both WEAK.
    """
    b23 = row.get("Score_Band_2023", "WEAK")
    b25 = row.get("Score_Band_2025", "WEAK")
    strong = {"STRONG"}
    if b23 in strong and b25 in strong:
        return "LEAD"
    if b23 in strong or b25 in strong:
        return "REVIEW"
    if b23 == "WEAK" and b25 == "WEAK":
        return "DROP"
    return "WATCH"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_dual_score_table(
    df_2025: Optional[pd.DataFrame] = None,
    df_2023: Optional[pd.DataFrame] = None,
    path_2025: str = DEFAULT_2025_PATH,
    path_2023: str = DEFAULT_2023_PATH,
    how: str = "inner",
) -> pd.DataFrame:
    """
    Build the canonical dual-score table.

    Parameters
    ----------
    df_2025 : optional, pre-scored 2025 DataFrame (output of `score_funds`).
              If None, loaded and scored from `path_2025`.
    df_2023 : optional, pre-loaded 2023 DataFrame with a `Score_2023` column.
              If None, loaded from `path_2023`.
    path_2025, path_2023 : file paths used if the DataFrames are not supplied.
    how : pandas merge how — default 'inner' (funds present in BOTH systems).
          Use 'outer' if you want every fund from either side.

    Returns
    -------
    pd.DataFrame with one row per joined fund and the columns listed in the
    module docstring. Columns whose source data is unavailable are omitted
    rather than filled with placeholders.
    """
    # ---- Load 2025 (scored) ----
    if df_2025 is None:
        df_2025 = load_and_score(path_2025)
    df_2025 = df_2025.copy()

    sym_col = CSV_COLUMNS["symbol"]
    name_col = CSV_COLUMNS["name"]
    cat_col = CSV_COLUMNS["category"]

    # Coverage is computed on raw scored df (needs metric columns intact).
    df_2025["_Coverage_2025"] = _compute_2025_coverage(df_2025)

    keep_2025 = {
        sym_col: "Symbol",
        name_col: "Name_2025",
        cat_col: "Category_2025",
        "Fund_Type": "Fund_Type",
        "Score_Final": "Score_2025_Final",
        "Score_Band": "Score_Band_2025",
        "_Coverage_2025": "Data_Coverage_2025",
    }
    cols_present_2025 = [c for c in keep_2025 if c in df_2025.columns]
    df_2025_slim = df_2025[cols_present_2025].rename(
        columns={k: v for k, v in keep_2025.items() if k in cols_present_2025}
    )

    # ---- Load 2023 (pre-scored) ----
    if df_2023 is None:
        if not os.path.exists(path_2023):
            raise FileNotFoundError(
                f"2023 scores file not found at {path_2023}. "
                "Provide df_2023 or path_2023 explicitly."
            )
        df_2023 = pd.read_csv(path_2023)
    df_2023 = df_2023.copy()

    if "Score_2023" not in df_2023.columns:
        raise ValueError(
            "2023 DataFrame is missing required 'Score_2023' column."
        )

    df_2023["Score_Band_2023"] = df_2023["Score_2023"].apply(get_score_band)
    if "Avail_Weight" in df_2023.columns:
        df_2023["Data_Coverage_2023"] = df_2023["Avail_Weight"] / 100.0
    else:
        df_2023["Data_Coverage_2023"] = np.nan

    keep_2023 = {
        "Symbol": "Symbol",
        "Name": "Name_2023",
        "Category Name": "Category_2023",
        "Score_2023": "Score_2023_Final",
        "Score_Band_2023": "Score_Band_2023",
        "Data_Coverage_2023": "Data_Coverage_2023",
    }
    cols_present_2023 = [c for c in keep_2023 if c in df_2023.columns]
    df_2023_slim = df_2023[cols_present_2023].rename(
        columns={k: v for k, v in keep_2023.items() if k in cols_present_2023}
    )

    # ---- Join ----
    merged = df_2023_slim.merge(df_2025_slim, on="Symbol", how=how)

    # Prefer 2025 metadata; fall back to 2023 where missing.
    merged["Name"] = merged.get("Name_2025")
    if "Name_2023" in merged.columns:
        merged["Name"] = merged["Name"].fillna(merged["Name_2023"])
    merged["Category"] = merged.get("Category_2025")
    if "Category_2023" in merged.columns:
        merged["Category"] = merged["Category"].fillna(merged["Category_2023"])

    # ---- Derived columns ----
    merged["Score_Gap"] = merged["Score_2025_Final"] - merged["Score_2023_Final"]

    # Dense ranks (1 = best). NaN scores get NaN rank.
    merged["Rank_2023"] = merged["Score_2023_Final"].rank(
        method="dense", ascending=False
    ).astype("Int64")
    merged["Rank_2025"] = merged["Score_2025_Final"].rank(
        method="dense", ascending=False
    ).astype("Int64")
    avg_rank = merged[["Rank_2023", "Rank_2025"]].astype(float).mean(axis=1)
    merged["Consensus_Rank"] = avg_rank.rank(
        method="dense", ascending=True
    ).astype("Int64")

    merged["Quadrant"] = [
        _classify_quadrant(s23, s25)
        for s23, s25 in zip(merged["Score_2023_Final"], merged["Score_2025_Final"])
    ]
    merged["Primary_Driver"] = merged.apply(_primary_driver, axis=1)
    merged["Action_Flag"] = merged.apply(_action_flag, axis=1)

    # ---- Final column order (only those that exist) ----
    ordered = [
        "Symbol", "Name", "Category", "Fund_Type",
        "Score_2023_Final", "Score_2025_Final", "Score_Gap",
        "Rank_2023", "Rank_2025", "Consensus_Rank",
        "Score_Band_2023", "Score_Band_2025", "Quadrant",
        "Data_Coverage_2023", "Data_Coverage_2025",
        "Primary_Driver", "Action_Flag",
    ]
    final_cols = [c for c in ordered if c in merged.columns]
    return merged[final_cols].sort_values("Consensus_Rank").reset_index(drop=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Build the canonical dual-score fund table (CSV)."
    )
    parser.add_argument("--path-2025", default=DEFAULT_2025_PATH,
                        help="CSV of raw 2025 fund data to score.")
    parser.add_argument("--path-2023", default=DEFAULT_2023_PATH,
                        help="CSV of pre-scored 2023 funds.")
    parser.add_argument("--how", default="inner", choices=["inner", "outer", "left", "right"],
                        help="Join strategy between the two systems.")
    parser.add_argument("--out", default=DEFAULT_OUTPUT_PATH,
                        help="Output CSV path.")
    args = parser.parse_args()

    table = build_dual_score_table(
        path_2025=args.path_2025,
        path_2023=args.path_2023,
        how=args.how,
    )
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    table.to_csv(args.out, index=False)
    print(f"Wrote {len(table):,} rows to {args.out}")


if __name__ == "__main__":
    _cli()
