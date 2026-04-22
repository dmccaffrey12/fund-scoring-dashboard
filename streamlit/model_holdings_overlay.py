"""
Model Holdings Overlay
======================
Join current model portfolio holdings against the canonical dual-score table
and produce the committee-review artifacts:

    model_holdings_scorecard.csv       one row per model holding, enriched
                                       with 2023/2025 scores, bands, quadrant,
                                       and an overlay-specific Action_Flag.
    model_summary.csv                  one row per model with target-weighted
                                       average 2023 / 2025 scores, coverage,
                                       and band/quadrant weight shares.
    current_holdings_review.csv        weak links — current holdings flagged
                                       for replacement or patience review.
    research_candidates.csv            top scorers in the universe NOT held
                                       by any model.
    replacement_candidates.csv         same-category replacement suggestions
                                       for each weak/weak current holding.

Design principle: the overlay is a *lens* on top of the scored fund universe,
not part of the scoring methodology. Both the 2023 and 2025 scores are kept
separately reviewable — we never collapse disagreement into a single number.

Public API:
    OVERLAY_SUBDIR
    ACTION_FLAGS
    build_model_overlay(df_holdings, dual_table) -> OverlayResult
    write_overlay(result, out_dir) -> Dict[str, str]
    load_overlay(out_dir) -> Dict[str, pd.DataFrame|dict]
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from model_holdings_intake import normalize_weights


OVERLAY_SUBDIR = "model_holdings"

SCORECARD_NAME = "model_holdings_scorecard.csv"
SUMMARY_NAME = "model_summary.csv"
CURRENT_REVIEW_NAME = "current_holdings_review.csv"
RESEARCH_CANDIDATES_NAME = "research_candidates.csv"
REPLACEMENT_CANDIDATES_NAME = "replacement_candidates.csv"
METADATA_NAME = "overlay_metadata.json"

# Committee action flags — deliberately *distinct* from the base-table
# Action_Flag column, which only looks at the scores. The overlay flags
# also consider whether the fund is currently held.
ACTION_HIGH_CONVICTION = "High_Conviction_Hold"
ACTION_PERF_LED = "Performance_Led_Hold_Review_Quality"
ACTION_QUALITY_LED = "Quality_Led_Hold_Review_Patience"
ACTION_REPLACEMENT = "Replacement_Candidate"
ACTION_RESEARCH = "Research_Candidate"
ACTION_REVIEW_COVERAGE = "Review_Missing_Score"

ACTION_FLAGS = (
    ACTION_HIGH_CONVICTION,
    ACTION_PERF_LED,
    ACTION_QUALITY_LED,
    ACTION_REPLACEMENT,
    ACTION_RESEARCH,
    ACTION_REVIEW_COVERAGE,
)

RESEARCH_TOP_N_DEFAULT = 25
REPLACEMENT_TOP_N_PER_CATEGORY = 3

SCORECARD_COLUMNS = [
    "Model_Name", "Symbol", "Fund_Name", "Sleeve", "Status",
    "Internal_Category", "Notes",
    "Target_Weight", "Target_Weight_Pct",
    "Name", "Category", "Fund_Type",
    "Score_2023_Final", "Score_2025_Final", "Score_Gap",
    "Rank_2023", "Rank_2025", "Consensus_Rank",
    "Score_Band_2023", "Score_Band_2025", "Quadrant",
    "Data_Coverage_2023", "Data_Coverage_2025",
    "Primary_Driver",
    "Scored_In_Universe",
    "Overlay_Action",
]

SUMMARY_COLUMNS = [
    "Model_Name",
    "Holding_Count",
    "Total_Target_Weight_Pct",
    "Scored_Holding_Count",
    "Scored_Weight_Pct",
    "Weighted_Score_2023",
    "Weighted_Score_2025",
    "Weight_Pct_Q1_Both_Strong",
    "Weight_Pct_Q2_Only_2025",
    "Weight_Pct_Q3_Only_2023",
    "Weight_Pct_Q4_Both_Weak",
    "Weight_Pct_Band_STRONG_2023",
    "Weight_Pct_Band_STRONG_2025",
    "Weight_Pct_Band_WEAK_2023",
    "Weight_Pct_Band_WEAK_2025",
    "Weight_Pct_HighConviction",
    "Weight_Pct_Replacement",
    "Weight_Pct_PerfLed",
    "Weight_Pct_QualityLed",
    "Weight_Pct_Unscored",
]


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class OverlayResult:
    scorecard: pd.DataFrame
    summary: pd.DataFrame
    current_review: pd.DataFrame
    research_candidates: pd.DataFrame
    replacement_candidates: pd.DataFrame
    metadata: Dict[str, Any] = field(default_factory=dict)

    def tables(self) -> Dict[str, pd.DataFrame]:
        return {
            "scorecard": self.scorecard,
            "summary": self.summary,
            "current_review": self.current_review,
            "research_candidates": self.research_candidates,
            "replacement_candidates": self.replacement_candidates,
        }


# ---------------------------------------------------------------------------
# Flag logic
# ---------------------------------------------------------------------------

def _assign_overlay_action(row: pd.Series) -> str:
    """Pick an overlay action flag for a currently-held holding row."""
    if not bool(row.get("Scored_In_Universe", False)):
        return ACTION_REVIEW_COVERAGE
    b23 = row.get("Score_Band_2023")
    b25 = row.get("Score_Band_2025")
    if b23 == "STRONG" and b25 == "STRONG":
        return ACTION_HIGH_CONVICTION
    if b23 == "STRONG" and b25 in {"REVIEW", "WEAK"}:
        return ACTION_PERF_LED
    if b25 == "STRONG" and b23 in {"REVIEW", "WEAK"}:
        return ACTION_QUALITY_LED
    if b23 == "WEAK" and b25 == "WEAK":
        return ACTION_REPLACEMENT
    # REVIEW/REVIEW or REVIEW mixed with WEAK — reviewable but not as
    # urgent as a straight replacement.
    if b23 == "WEAK" or b25 == "WEAK":
        return ACTION_REPLACEMENT
    return ACTION_PERF_LED if (b23 == "REVIEW" and b25 == "REVIEW") else ACTION_PERF_LED


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _ensure_string_symbol(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def _build_scorecard(
    holdings: pd.DataFrame,
    dual_table: pd.DataFrame,
) -> pd.DataFrame:
    h = normalize_weights(holdings).copy()
    h["Symbol"] = _ensure_string_symbol(h["Symbol"])

    d = dual_table.copy()
    if "Symbol" in d.columns:
        d["Symbol"] = _ensure_string_symbol(d["Symbol"])

    # Keep only join-relevant columns from the dual table so we don't
    # collide with holding-side columns (e.g. Fund_Name vs Name).
    dual_cols = [
        c for c in [
            "Symbol", "Name", "Category", "Fund_Type",
            "Score_2023_Final", "Score_2025_Final", "Score_Gap",
            "Rank_2023", "Rank_2025", "Consensus_Rank",
            "Score_Band_2023", "Score_Band_2025", "Quadrant",
            "Data_Coverage_2023", "Data_Coverage_2025",
            "Primary_Driver",
        ]
        if c in d.columns
    ]
    d_slim = d[dual_cols]

    merged = h.merge(d_slim, on="Symbol", how="left")
    merged["Scored_In_Universe"] = merged.get("Score_2025_Final").notna() | \
        merged.get("Score_2023_Final").notna()

    merged["Overlay_Action"] = merged.apply(_assign_overlay_action, axis=1)

    # Fill in optional / absent columns so downstream writers have a
    # consistent schema regardless of upload shape.
    for col in SCORECARD_COLUMNS:
        if col not in merged.columns:
            merged[col] = np.nan

    # Deterministic sort: model name, then descending consensus (best first),
    # then by symbol to break ties. Unscored rows sink to the bottom.
    merged["_consensus_sort"] = merged["Consensus_Rank"].astype(float)
    merged = merged.sort_values(
        ["Model_Name", "_consensus_sort", "Symbol"],
        ascending=[True, True, True],
        kind="stable",
        na_position="last",
    ).drop(columns="_consensus_sort").reset_index(drop=True)

    return merged[SCORECARD_COLUMNS]


def _weighted_mean(values: pd.Series, weights: pd.Series) -> Optional[float]:
    mask = values.notna() & weights.notna() & (weights > 0)
    if not mask.any():
        return None
    v = values[mask].astype(float)
    w = weights[mask].astype(float)
    total = float(w.sum())
    if total <= 0:
        return None
    return float((v * w).sum() / total)


def _weight_share(weights: pd.Series, mask: pd.Series) -> float:
    total = float(weights.fillna(0.0).sum())
    if total <= 0:
        return 0.0
    return float(weights.where(mask, 0.0).fillna(0.0).sum() / total) * 100.0


def _build_summary(scorecard: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if scorecard.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    grouped = scorecard.groupby("Model_Name", dropna=False, sort=True)
    for model, block in grouped:
        weights = block["Target_Weight"].astype(float)
        weights_pct = block["Target_Weight_Pct"].astype(float)
        scored_mask = block["Scored_In_Universe"].fillna(False).astype(bool)
        q_col = block.get("Quadrant")
        b23_col = block.get("Score_Band_2023")
        b25_col = block.get("Score_Band_2025")
        act = block["Overlay_Action"]

        row = {
            "Model_Name": model,
            "Holding_Count": int(len(block)),
            "Total_Target_Weight_Pct": float(weights_pct.fillna(0.0).sum()),
            "Scored_Holding_Count": int(scored_mask.sum()),
            "Scored_Weight_Pct": float(weights_pct.where(scored_mask, 0.0).fillna(0.0).sum()),
            "Weighted_Score_2023": _weighted_mean(block["Score_2023_Final"], weights),
            "Weighted_Score_2025": _weighted_mean(block["Score_2025_Final"], weights),
            "Weight_Pct_Q1_Both_Strong":
                _weight_share(weights_pct, q_col == "Q1_Both_Strong") if q_col is not None else 0.0,
            "Weight_Pct_Q2_Only_2025":
                _weight_share(weights_pct, q_col == "Q2_Only_2025") if q_col is not None else 0.0,
            "Weight_Pct_Q3_Only_2023":
                _weight_share(weights_pct, q_col == "Q3_Only_2023") if q_col is not None else 0.0,
            "Weight_Pct_Q4_Both_Weak":
                _weight_share(weights_pct, q_col == "Q4_Both_Weak") if q_col is not None else 0.0,
            "Weight_Pct_Band_STRONG_2023":
                _weight_share(weights_pct, b23_col == "STRONG") if b23_col is not None else 0.0,
            "Weight_Pct_Band_STRONG_2025":
                _weight_share(weights_pct, b25_col == "STRONG") if b25_col is not None else 0.0,
            "Weight_Pct_Band_WEAK_2023":
                _weight_share(weights_pct, b23_col == "WEAK") if b23_col is not None else 0.0,
            "Weight_Pct_Band_WEAK_2025":
                _weight_share(weights_pct, b25_col == "WEAK") if b25_col is not None else 0.0,
            "Weight_Pct_HighConviction":
                _weight_share(weights_pct, act == ACTION_HIGH_CONVICTION),
            "Weight_Pct_Replacement":
                _weight_share(weights_pct, act == ACTION_REPLACEMENT),
            "Weight_Pct_PerfLed":
                _weight_share(weights_pct, act == ACTION_PERF_LED),
            "Weight_Pct_QualityLed":
                _weight_share(weights_pct, act == ACTION_QUALITY_LED),
            "Weight_Pct_Unscored":
                _weight_share(weights_pct, ~scored_mask),
        }
        rows.append(row)

    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS).sort_values(
        "Model_Name", kind="stable",
    ).reset_index(drop=True)


def _build_current_review(scorecard: pd.DataFrame) -> pd.DataFrame:
    """Holdings that need committee attention (everything except HighConviction)."""
    if scorecard.empty:
        return scorecard.head(0)
    mask = scorecard["Overlay_Action"].isin([
        ACTION_PERF_LED, ACTION_QUALITY_LED,
        ACTION_REPLACEMENT, ACTION_REVIEW_COVERAGE,
    ])
    sub = scorecard.loc[mask].copy()
    priority = {
        ACTION_REPLACEMENT: 0,
        ACTION_REVIEW_COVERAGE: 1,
        ACTION_QUALITY_LED: 2,
        ACTION_PERF_LED: 3,
    }
    sub["_priority"] = sub["Overlay_Action"].map(priority).fillna(9).astype(int)
    sub = sub.sort_values(
        ["_priority", "Model_Name", "Target_Weight_Pct", "Symbol"],
        ascending=[True, True, False, True],
        kind="stable",
    ).drop(columns="_priority").reset_index(drop=True)
    return sub


def _build_research_candidates(
    dual_table: pd.DataFrame,
    held_symbols: set,
    top_n: int = RESEARCH_TOP_N_DEFAULT,
) -> pd.DataFrame:
    if dual_table.empty or "Consensus_Rank" not in dual_table.columns:
        cols = [
            c for c in [
                "Symbol", "Name", "Category", "Fund_Type",
                "Score_2023_Final", "Score_2025_Final",
                "Rank_2023", "Rank_2025", "Consensus_Rank",
                "Score_Band_2023", "Score_Band_2025", "Quadrant",
                "Primary_Driver",
            ] if c in dual_table.columns
        ]
        return pd.DataFrame(columns=cols)

    d = dual_table.copy()
    d["Symbol"] = _ensure_string_symbol(d["Symbol"])
    unheld = d[~d["Symbol"].isin(held_symbols)].copy()
    if "Score_Band_2023" in unheld.columns and "Score_Band_2025" in unheld.columns:
        unheld = unheld[(unheld["Score_Band_2023"] == "STRONG") |
                        (unheld["Score_Band_2025"] == "STRONG")]
    unheld = unheld.sort_values(
        ["Consensus_Rank", "Symbol"],
        ascending=[True, True],
        kind="stable",
        na_position="last",
    ).head(top_n).reset_index(drop=True)

    wanted = [
        "Symbol", "Name", "Category", "Fund_Type",
        "Score_2023_Final", "Score_2025_Final",
        "Rank_2023", "Rank_2025", "Consensus_Rank",
        "Score_Band_2023", "Score_Band_2025", "Quadrant",
        "Primary_Driver",
    ]
    cols = [c for c in wanted if c in unheld.columns]
    return unheld[cols]


def _build_replacement_candidates(
    scorecard: pd.DataFrame,
    dual_table: pd.DataFrame,
    top_per_category: int = REPLACEMENT_TOP_N_PER_CATEGORY,
) -> pd.DataFrame:
    """For each replacement-flagged current holding with a Category, list the
    top-N unheld same-category funds ranked by Consensus_Rank.
    """
    empty_cols = [
        "Model_Name", "Current_Symbol", "Current_Name", "Current_Category",
        "Current_Score_2023_Final", "Current_Score_2025_Final",
        "Current_Score_Band_2023", "Current_Score_Band_2025",
        "Candidate_Rank", "Candidate_Symbol", "Candidate_Name",
        "Candidate_Category", "Candidate_Fund_Type",
        "Candidate_Score_2023_Final", "Candidate_Score_2025_Final",
        "Candidate_Consensus_Rank",
        "Candidate_Score_Band_2023", "Candidate_Score_Band_2025",
        "Candidate_Quadrant",
    ]
    if scorecard.empty or dual_table.empty:
        return pd.DataFrame(columns=empty_cols)
    if "Category" not in dual_table.columns or "Consensus_Rank" not in dual_table.columns:
        return pd.DataFrame(columns=empty_cols)

    held_symbols = set(_ensure_string_symbol(scorecard["Symbol"]))
    d = dual_table.copy()
    d["Symbol"] = _ensure_string_symbol(d["Symbol"])
    pool = d[~d["Symbol"].isin(held_symbols)].copy()
    pool = pool.sort_values(
        ["Category", "Consensus_Rank", "Symbol"],
        ascending=[True, True, True],
        kind="stable",
        na_position="last",
    )

    rows: List[Dict[str, Any]] = []
    mask = scorecard["Overlay_Action"] == ACTION_REPLACEMENT
    targets = scorecard.loc[mask]
    for _, h in targets.iterrows():
        cat = h.get("Category")
        if pd.isna(cat) or not str(cat).strip():
            continue
        candidates = pool[pool["Category"] == cat].head(top_per_category)
        for rank_idx, (_, c) in enumerate(candidates.iterrows(), start=1):
            rows.append({
                "Model_Name": h.get("Model_Name"),
                "Current_Symbol": h.get("Symbol"),
                "Current_Name": h.get("Name"),
                "Current_Category": cat,
                "Current_Score_2023_Final": h.get("Score_2023_Final"),
                "Current_Score_2025_Final": h.get("Score_2025_Final"),
                "Current_Score_Band_2023": h.get("Score_Band_2023"),
                "Current_Score_Band_2025": h.get("Score_Band_2025"),
                "Candidate_Rank": rank_idx,
                "Candidate_Symbol": c.get("Symbol"),
                "Candidate_Name": c.get("Name"),
                "Candidate_Category": c.get("Category"),
                "Candidate_Fund_Type": c.get("Fund_Type"),
                "Candidate_Score_2023_Final": c.get("Score_2023_Final"),
                "Candidate_Score_2025_Final": c.get("Score_2025_Final"),
                "Candidate_Consensus_Rank": c.get("Consensus_Rank"),
                "Candidate_Score_Band_2023": c.get("Score_Band_2023"),
                "Candidate_Score_Band_2025": c.get("Score_Band_2025"),
                "Candidate_Quadrant": c.get("Quadrant"),
            })
    if not rows:
        return pd.DataFrame(columns=empty_cols)
    out = pd.DataFrame(rows, columns=empty_cols)
    return out.sort_values(
        ["Model_Name", "Current_Symbol", "Candidate_Rank"],
        ascending=[True, True, True],
        kind="stable",
    ).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_model_overlay(
    df_holdings: pd.DataFrame,
    dual_table: pd.DataFrame,
    *,
    research_top_n: int = RESEARCH_TOP_N_DEFAULT,
    replacement_top_per_category: int = REPLACEMENT_TOP_N_PER_CATEGORY,
) -> OverlayResult:
    """Join holdings with the dual-score table and compute overlay artifacts.

    Neither input is mutated. Missing optional holding columns are tolerated;
    unknown symbols (not in the scored universe) show up with
    ``Overlay_Action = Review_Missing_Score`` rather than silently dropping.
    """
    scorecard = _build_scorecard(df_holdings, dual_table)
    summary = _build_summary(scorecard)
    current_review = _build_current_review(scorecard)

    held_symbols = set(_ensure_string_symbol(scorecard["Symbol"])) if not scorecard.empty else set()
    research = _build_research_candidates(
        dual_table, held_symbols, top_n=research_top_n,
    )
    replacements = _build_replacement_candidates(
        scorecard, dual_table, top_per_category=replacement_top_per_category,
    )

    metadata = {
        "model_count": int(scorecard["Model_Name"].nunique()) if not scorecard.empty else 0,
        "holding_row_count": int(len(scorecard)),
        "scored_holding_count": int(scorecard["Scored_In_Universe"].fillna(False).astype(bool).sum())
            if not scorecard.empty else 0,
        "replacement_row_count": int(len(replacements)),
        "research_candidate_count": int(len(research)),
        "current_review_count": int(len(current_review)),
        "universe_row_count": int(len(dual_table)),
        "action_flag_counts": {
            str(k): int(v)
            for k, v in (scorecard["Overlay_Action"].value_counts(dropna=False).items()
                          if not scorecard.empty else [])
        },
    }

    return OverlayResult(
        scorecard=scorecard,
        summary=summary,
        current_review=current_review,
        research_candidates=research,
        replacement_candidates=replacements,
        metadata=metadata,
    )


def write_overlay(result: OverlayResult, out_dir: str) -> Dict[str, str]:
    """Persist overlay artifacts to ``out_dir``. Returns {name: path}."""
    os.makedirs(out_dir, exist_ok=True)
    paths: Dict[str, str] = {}

    mapping = {
        "scorecard": (SCORECARD_NAME, result.scorecard),
        "summary": (SUMMARY_NAME, result.summary),
        "current_review": (CURRENT_REVIEW_NAME, result.current_review),
        "research_candidates": (RESEARCH_CANDIDATES_NAME, result.research_candidates),
        "replacement_candidates": (REPLACEMENT_CANDIDATES_NAME, result.replacement_candidates),
    }
    for key, (fname, df) in mapping.items():
        path = os.path.join(out_dir, fname)
        df.to_csv(path, index=False)
        paths[key] = path

    meta_path = os.path.join(out_dir, METADATA_NAME)
    with open(meta_path, "w") as f:
        json.dump(result.metadata, f, indent=2, sort_keys=True, default=str)
    paths["metadata"] = meta_path
    return paths


def load_overlay(out_dir: str) -> Optional[Dict[str, Any]]:
    """Load previously-persisted overlay artifacts from ``out_dir``.

    Returns None if the directory is missing or has no scorecard.
    """
    if not os.path.isdir(out_dir):
        return None
    scorecard_path = os.path.join(out_dir, SCORECARD_NAME)
    if not os.path.isfile(scorecard_path):
        return None

    def _safe_read(fname: str) -> pd.DataFrame:
        path = os.path.join(out_dir, fname)
        if not os.path.isfile(path):
            return pd.DataFrame()
        try:
            return pd.read_csv(path)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()

    meta: Dict[str, Any] = {}
    meta_path = os.path.join(out_dir, METADATA_NAME)
    if os.path.isfile(meta_path):
        try:
            with open(meta_path) as f:
                meta = json.load(f)
        except json.JSONDecodeError:
            meta = {}

    return {
        "path": out_dir,
        "scorecard": _safe_read(SCORECARD_NAME),
        "summary": _safe_read(SUMMARY_NAME),
        "current_review": _safe_read(CURRENT_REVIEW_NAME),
        "research_candidates": _safe_read(RESEARCH_CANDIDATES_NAME),
        "replacement_candidates": _safe_read(REPLACEMENT_CANDIDATES_NAME),
        "metadata": meta,
    }
