"""
Historical Tracking
===================
Saves and compares scored fund snapshots over time using JSON persistence.
Snapshots are stored in a `snapshots/` directory relative to this file.
"""

import json
import os
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from scoring_engine import CSV_COLUMNS

# ---------------------------------------------------------------------------
# Directory setup
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOTS_DIR = os.path.join(_HERE, "snapshots")

os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

SYM_COL = CSV_COLUMNS["symbol"]
NAME_COL = CSV_COLUMNS["name"]
CAT_COL = CSV_COLUMNS["category"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _snapshot_path(date_str: str) -> str:
    return os.path.join(SNAPSHOTS_DIR, f"{date_str}.json")


def _sanitize_value(v):
    """Convert numpy types to native Python for JSON serialization."""
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return None
    return v


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_snapshot(scored_df: pd.DataFrame, label: Optional[str] = None) -> str:
    """
    Save current scores to a JSON snapshot file.

    Parameters
    ----------
    scored_df : Scored DataFrame (output of score_funds)
    label     : Human-readable label, e.g. "March 2026". Defaults to current month/year.

    Returns
    -------
    date_str  : The snapshot ID (date string, e.g. "2026-03-24")
    """
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    if label is None:
        label = now.strftime("%B %Y")

    scores_dict = {}
    for _, row in scored_df.iterrows():
        sym = row.get(SYM_COL)
        if pd.isna(sym):
            continue
        score = row.get("Score_Final")
        band = row.get("Score_Band", "WEAK")
        category = row.get(CAT_COL, "")
        fund_type = row.get("Fund_Type", "")
        name = row.get(NAME_COL, "")
        scores_dict[str(sym)] = {
            "score": _sanitize_value(score),
            "band": str(band) if pd.notna(band) else "WEAK",
            "category": str(category) if pd.notna(category) else "",
            "type": str(fund_type) if pd.notna(fund_type) else "",
            "name": str(name) if pd.notna(name) else "",
        }

    valid_scores = [
        v["score"] for v in scores_dict.values()
        if v["score"] is not None
    ]
    avg_score = round(float(np.mean(valid_scores)), 2) if valid_scores else None

    snapshot = {
        "date": date_str,
        "label": label,
        "fund_count": len(scores_dict),
        "avg_score": avg_score,
        "scores": scores_dict,
    }

    path = _snapshot_path(date_str)
    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2)

    return date_str


def list_snapshots() -> list:
    """
    Return a list of snapshot metadata dicts (no scores), sorted newest first.

    Returns
    -------
    list of {date, label, fund_count, avg_score}
    """
    results = []
    if not os.path.exists(SNAPSHOTS_DIR):
        return results

    for fname in sorted(os.listdir(SNAPSHOTS_DIR), reverse=True):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(SNAPSHOTS_DIR, fname)
        try:
            with open(fpath, "r") as f:
                data = json.load(f)
            results.append({
                "date": data.get("date", fname.replace(".json", "")),
                "label": data.get("label", ""),
                "fund_count": data.get("fund_count", 0),
                "avg_score": data.get("avg_score"),
            })
        except Exception:
            continue

    return results


def load_snapshot(date_str: str) -> dict:
    """
    Load a full snapshot by date string.

    Parameters
    ----------
    date_str : e.g. "2026-03-24"

    Returns
    -------
    Full snapshot dict including 'scores' dict
    """
    path = _snapshot_path(date_str)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Snapshot not found: {date_str}")
    with open(path, "r") as f:
        return json.load(f)


def get_fund_history(scored_df: pd.DataFrame, symbol: str) -> list:
    """
    Return score history for a fund across all snapshots.

    Parameters
    ----------
    scored_df : Current scored DataFrame (used to resolve fund name/category)
    symbol    : Ticker symbol

    Returns
    -------
    list of {date, label, score, band} sorted chronologically
    """
    history = []
    if not os.path.exists(SNAPSHOTS_DIR):
        return history

    for fname in sorted(os.listdir(SNAPSHOTS_DIR)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(SNAPSHOTS_DIR, fname)
        try:
            with open(fpath, "r") as f:
                data = json.load(f)
            scores = data.get("scores", {})
            if symbol in scores:
                entry = scores[symbol]
                history.append({
                    "date": data.get("date", fname.replace(".json", "")),
                    "label": data.get("label", ""),
                    "score": entry.get("score"),
                    "band": entry.get("band", "WEAK"),
                })
        except Exception:
            continue

    return history


def compare_snapshots(date1: str, date2: str) -> pd.DataFrame:
    """
    Compare two snapshots and return a DataFrame of score changes.

    Parameters
    ----------
    date1 : Earlier snapshot date string
    date2 : Later snapshot date string

    Returns
    -------
    DataFrame with columns: Symbol, Name, Category, Type,
                            Score_Earlier, Score_Later, Change
    Sorted by |Change| descending.
    """
    snap1 = load_snapshot(date1)
    snap2 = load_snapshot(date2)

    scores1 = snap1.get("scores", {})
    scores2 = snap2.get("scores", {})

    all_symbols = set(scores1.keys()) | set(scores2.keys())

    rows = []
    for sym in all_symbols:
        s1_data = scores1.get(sym, {})
        s2_data = scores2.get(sym, {})
        s1 = s1_data.get("score")
        s2 = s2_data.get("score")

        if s1 is None and s2 is None:
            continue

        name = s2_data.get("name") or s1_data.get("name", "")
        category = s2_data.get("category") or s1_data.get("category", "")
        fund_type = s2_data.get("type") or s1_data.get("type", "")
        band_earlier = s1_data.get("band", "")
        band_later = s2_data.get("band", "")

        change = None
        if s1 is not None and s2 is not None:
            change = round(s2 - s1, 2)

        rows.append({
            "Symbol": sym,
            "Name": name,
            "Category": category,
            "Type": fund_type,
            "Score_Earlier": s1,
            "Score_Later": s2,
            "Band_Earlier": band_earlier,
            "Band_Later": band_later,
            "Change": change,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["_abs_change"] = df["Change"].abs().fillna(-1)
    df = df.sort_values("_abs_change", ascending=False).drop(columns=["_abs_change"])
    return df.reset_index(drop=True)
