"""
Score Explanation Engine
========================
Generates human-readable narratives explaining WHY a fund scores the way it does.
All explanations are deterministic f-string templates — no AI/LLM required.
"""

import math
import numpy as np
import pandas as pd

from scoring_engine import (
    ACTIVE_METRICS,
    CSV_COLUMNS,
    PASSIVE_METRICS,
    PASSIVE_RESCALE,
    calculate_percentile,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Friendly display labels for metric keys
METRIC_LABELS = {
    "expense_ratio": "Expense Ratio",
    "tracking_error_3y": "Tracking Error (3Y)",
    "tracking_error_5y": "Tracking Error (5Y)",
    "tracking_error_10y": "Tracking Error (10Y)",
    "r_squared_5y": "R-Squared (5Y)",
    "aum": "Assets Under Management",
    "downside_5y": "Downside Capture (5Y)",
    "downside_10y": "Downside Capture (10Y)",
    "max_drawdown_5y": "Max Drawdown (5Y)",
    "max_drawdown_10y": "Max Drawdown (10Y)",
    "info_ratio_3y": "Information Ratio (3Y)",
    "info_ratio_5y": "Information Ratio (5Y)",
    "info_ratio_10y": "Information Ratio (10Y)",
    "sortino_3y": "Sortino Ratio (3Y)",
    "sortino_5y": "Sortino Ratio (5Y)",
    "sortino_10y": "Sortino Ratio (10Y)",
    "upside_5y": "Upside Capture (5Y)",
    "upside_10y": "Upside Capture (10Y)",
    "returns_3y": "3Y Total Return",
    "returns_5y": "5Y Total Return",
    "returns_10y": "10Y Total Return",
}


def _pctile_label(pctile_0_to_100: float) -> str:
    """Return ordinal string: 99th, 82nd, 51st, etc."""
    p = round(pctile_0_to_100)
    if 11 <= (p % 100) <= 13:
        return f"{p}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(p % 10, "th")
    return f"{p}{suffix}"


def _er_interpretation(pctile: float) -> str:
    if pctile >= 90:
        return "best-in-class cost efficiency"
    if pctile >= 70:
        return "a competitive, below-average expense ratio"
    if pctile >= 40:
        return "a roughly average expense ratio for its peer group"
    if pctile >= 20:
        return "an above-average cost relative to peers"
    return "one of the most expensive funds in its category"


def _te_interpretation(pctile: float) -> str:
    if pctile >= 90:
        return "exceptional tracking accuracy — minimal deviation from its benchmark"
    if pctile >= 70:
        return "strong tracking accuracy, hugging its benchmark closely"
    if pctile >= 40:
        return "average tracking accuracy relative to category peers"
    if pctile >= 20:
        return "slightly above-average tracking error, introducing benchmark risk"
    return "significant tracking error, suggesting material benchmark deviation"


def _drawdown_interpretation(pctile: float) -> str:
    if pctile >= 90:
        return "exceptional downside protection during market stress"
    if pctile >= 70:
        return "better-than-average protection during market drawdowns"
    if pctile >= 40:
        return "average drawdown behavior relative to peers"
    if pctile >= 20:
        return "deeper drawdowns than most peers — elevated tail risk"
    return "among the worst drawdown profiles in its category"


def _sortino_interpretation(pctile: float) -> str:
    if pctile >= 90:
        return "exceptional risk-adjusted returns on the downside"
    if pctile >= 70:
        return "strong risk-adjusted return quality"
    if pctile >= 40:
        return "average risk-adjusted return profile"
    if pctile >= 20:
        return "below-average risk-adjusted returns"
    return "poor risk-adjusted return quality relative to peers"


def _ir_interpretation(pctile: float) -> str:
    if pctile >= 90:
        return "consistent outperformance vs. benchmark on a risk-adjusted basis"
    if pctile >= 70:
        return "meaningful, consistent active value added"
    if pctile >= 40:
        return "average active management consistency"
    if pctile >= 20:
        return "inconsistent benchmark-relative performance"
    return "persistent underperformance vs. the benchmark"


def _capture_interpretation(pctile: float, capture_type: str) -> str:
    if capture_type == "downside":
        if pctile >= 90:
            return "excellent — captures very little of market downturns"
        if pctile >= 70:
            return "good — below-average sensitivity to market declines"
        if pctile >= 40:
            return "average downside sensitivity"
        if pctile >= 20:
            return "above-average participation in market declines"
        return "high downside capture — amplifies market losses"
    else:  # upside
        if pctile >= 90:
            return "exceptional — captures most market upside moves"
        if pctile >= 70:
            return "strong upside participation"
        if pctile >= 40:
            return "average upside capture"
        if pctile >= 20:
            return "below-average participation in market rallies"
        return "poor upside capture — misses most market gains"


def _aum_interpretation(pctile: float) -> str:
    if pctile >= 90:
        return "one of the largest and most liquid funds in its category"
    if pctile >= 70:
        return "comfortably large with strong liquidity"
    if pctile >= 40:
        return "moderate size relative to peers"
    if pctile >= 20:
        return "smaller fund with limited liquidity"
    return "a small fund with potential liquidity constraints"


def _returns_interpretation(pctile: float) -> str:
    if pctile >= 90:
        return "top-decile absolute returns in its category"
    if pctile >= 70:
        return "above-average absolute returns"
    if pctile >= 40:
        return "average returns vs. category peers"
    if pctile >= 20:
        return "below-average total returns"
    return "among the weakest return profiles in its category"


def _r_squared_interpretation(pctile: float) -> str:
    if pctile >= 90:
        return "very high benchmark correlation — true index behavior"
    if pctile >= 70:
        return "strong index-like correlation to benchmark"
    if pctile >= 40:
        return "moderate benchmark correlation"
    if pctile >= 20:
        return "lower-than-expected benchmark correlation for an index fund"
    return "unusually low benchmark correlation for a passive fund"


def _build_metric_sentence(key: str, pctile: float, val, symbol: str) -> str:
    """Generate a single English sentence for a metric's contribution."""
    label = METRIC_LABELS.get(key, key)
    pord = _pctile_label(pctile)

    if key == "expense_ratio":
        er_pct = f"{val * 100:.3f}%" if pd.notna(val) else "N/A"
        interp = _er_interpretation(pctile)
        return (
            f"At {er_pct}, {symbol}'s expense ratio ranks in the {pord} percentile "
            f"of its category — {interp}."
        )
    elif key in ("tracking_error_3y", "tracking_error_5y", "tracking_error_10y"):
        period = key.split("_")[-1].upper()
        interp = _te_interpretation(pctile)
        val_str = f"{val:.2f}" if pd.notna(val) else "N/A"
        return (
            f"Tracking error ({period}) of {val_str} ranks in the {pord} percentile "
            f"of its category — {interp}."
        )
    elif key in ("max_drawdown_5y", "max_drawdown_10y"):
        period = "5Y" if "5y" in key else "10Y"
        interp = _drawdown_interpretation(pctile)
        val_str = f"{val:.2%}" if pd.notna(val) else "N/A"
        return (
            f"Max drawdown ({period}) of {val_str} ranks in the {pord} percentile — "
            f"{interp}."
        )
    elif key in ("sortino_3y", "sortino_5y", "sortino_10y"):
        period = key.split("_")[-1].upper()
        interp = _sortino_interpretation(pctile)
        val_str = f"{val:.2f}" if pd.notna(val) else "N/A"
        return (
            f"Sortino ratio ({period}) of {val_str} ranks in the {pord} percentile — "
            f"{interp}."
        )
    elif key in ("info_ratio_3y", "info_ratio_5y", "info_ratio_10y"):
        period = key.split("_")[-1].upper()
        interp = _ir_interpretation(pctile)
        val_str = f"{val:.2f}" if pd.notna(val) else "N/A"
        return (
            f"Information ratio ({period}) of {val_str} ranks in the {pord} percentile — "
            f"{interp}."
        )
    elif key in ("downside_5y", "downside_10y"):
        period = "5Y" if "5y" in key else "10Y"
        interp = _capture_interpretation(pctile, "downside")
        val_str = f"{val:.3f}" if pd.notna(val) else "N/A"
        return (
            f"Downside capture ({period}) of {val_str} ranks in the {pord} percentile — "
            f"{interp}."
        )
    elif key in ("upside_5y", "upside_10y"):
        period = "5Y" if "5y" in key else "10Y"
        interp = _capture_interpretation(pctile, "upside")
        val_str = f"{val:.3f}" if pd.notna(val) else "N/A"
        return (
            f"Upside capture ({period}) of {val_str} ranks in the {pord} percentile — "
            f"{interp}."
        )
    elif key == "aum":
        interp = _aum_interpretation(pctile)
        if pd.notna(val):
            if val >= 1e9:
                val_str = f"${val/1e9:.2f}B"
            elif val >= 1e6:
                val_str = f"${val/1e6:.0f}M"
            else:
                val_str = f"${val:,.0f}"
        else:
            val_str = "N/A"
        return (
            f"AUM of {val_str} ranks in the {pord} percentile — {interp}."
        )
    elif key in ("returns_3y", "returns_5y", "returns_10y"):
        period = key.split("_")[0].upper() + " " + key.split("_")[1].upper()
        interp = _returns_interpretation(pctile)
        val_str = f"{val * 100:.2f}%" if pd.notna(val) else "N/A"
        return (
            f"Total return ({period}) of {val_str} ranks in the {pord} percentile — "
            f"{interp}."
        )
    elif key == "r_squared_5y":
        interp = _r_squared_interpretation(pctile)
        val_str = f"{val:.4f}" if pd.notna(val) else "N/A"
        return (
            f"R-squared (5Y) of {val_str} ranks in the {pord} percentile — {interp}."
        )
    else:
        return (
            f"{label} ranks in the {pord} percentile of its category."
        )


# ---------------------------------------------------------------------------
# Per-fund percentile breakdown
# ---------------------------------------------------------------------------

def _get_fund_breakdown(scored_df: pd.DataFrame, symbol: str) -> dict:
    """
    Returns {metric_key: {percentile, weight, direction, raw_value, contribution}}
    for the fund's applicable metric set (Passive or Active).
    """
    sym_col = CSV_COLUMNS["symbol"]
    cat_col = CSV_COLUMNS["category"]

    row = scored_df[scored_df[sym_col] == symbol]
    if row.empty:
        return {}

    row = row.iloc[0]
    fund_type = row.get("Fund_Type", "Active")
    metrics = PASSIVE_METRICS if fund_type == "Passive" else ACTIVE_METRICS
    rescale = PASSIVE_RESCALE if fund_type == "Passive" else 1.0

    category = row[cat_col]
    cat_df = scored_df[scored_df[cat_col] == category]

    result = {}
    available_weight = 0.0

    for key, weight, direction in metrics:
        col = CSV_COLUMNS.get(key, key)
        if col not in scored_df.columns:
            continue
        val = row.get(col)
        if pd.isna(val):
            continue

        cat_vals = cat_df[col].dropna()
        if len(cat_vals) == 0:
            continue

        if direction == "higher":
            pctile = (cat_vals <= val).sum() / len(cat_vals)
        else:
            pctile = (cat_vals >= val).sum() / len(cat_vals)

        available_weight += weight
        result[key] = {
            "percentile": round(pctile * 100, 1),
            "weight": weight,
            "direction": direction,
            "raw_value": val,
            "col": col,
        }

    # Compute contribution points for each metric
    for key, info in result.items():
        if available_weight > 0:
            contrib = (info["percentile"] / 100) * info["weight"] / available_weight * 100 * rescale
        else:
            contrib = 0.0
        info["contribution"] = round(contrib, 2)

    return result, available_weight


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def explain_score(scored_df: pd.DataFrame, symbol: str) -> dict:
    """
    Returns a dict with summary, strengths, weaknesses, data_coverage,
    and fund_type_note for a given fund symbol.
    """
    sym_col = CSV_COLUMNS["symbol"]
    cat_col = CSV_COLUMNS["category"]
    name_col = CSV_COLUMNS["name"]

    row_match = scored_df[scored_df[sym_col] == symbol]
    if row_match.empty:
        return {"error": f"No fund found for symbol '{symbol}'"}

    row = row_match.iloc[0]
    fund_type = row.get("Fund_Type", "Active")
    category = row.get(cat_col, "Unknown")
    name = row.get(name_col, symbol)
    score = row.get("Score_Final")
    band = row.get("Score_Band", "WEAK")

    metrics = PASSIVE_METRICS if fund_type == "Passive" else ACTIVE_METRICS
    total_metrics = len(metrics)

    breakdown_result = _get_fund_breakdown(scored_df, symbol)
    if isinstance(breakdown_result, dict) and "error" in breakdown_result:
        return breakdown_result

    breakdown, available_weight = breakdown_result
    n_with_data = len(breakdown)
    coverage_pct = round(n_with_data / total_metrics * 100, 1) if total_metrics > 0 else 0

    missing_keys = [
        METRIC_LABELS.get(k, k) for k, _, _ in metrics
        if k not in breakdown
    ]

    # Sort by contribution to find top/bottom
    sorted_metrics = sorted(breakdown.items(), key=lambda x: x[1]["contribution"], reverse=True)
    top3 = sorted_metrics[:3]
    bottom3 = sorted_metrics[-3:][::-1]  # lowest first -> reverse so worst is first

    strengths = []
    for key, info in top3:
        strengths.append({
            "metric": METRIC_LABELS.get(key, key),
            "percentile": info["percentile"],
            "weight": info["weight"],
            "contribution_points": info["contribution"],
            "sentence": _build_metric_sentence(key, info["percentile"], info["raw_value"], symbol),
        })

    weaknesses = []
    for key, info in bottom3:
        weaknesses.append({
            "metric": METRIC_LABELS.get(key, key),
            "percentile": info["percentile"],
            "weight": info["weight"],
            "contribution_points": info["contribution"],
            "sentence": _build_metric_sentence(key, info["percentile"], info["raw_value"], symbol),
        })

    # Build summary
    score_str = f"{score:.1f}" if pd.notna(score) else "N/A"

    # Top driver description
    if top3:
        top_key, top_info = top3[0]
        top_label = METRIC_LABELS.get(top_key, top_key)
        top_pctile_label = _pctile_label(top_info["percentile"])
        top_driver_str = f"{top_label} ({top_pctile_label} percentile)"
    else:
        top_driver_str = "limited data"

    # Main drag description
    if bottom3:
        bot_key, bot_info = bottom3[0]
        bot_label = METRIC_LABELS.get(bot_key, bot_key)
        bot_pctile_label = _pctile_label(bot_info["percentile"])
        bot_driver_str = f"{bot_label} ({bot_pctile_label} percentile)"
        drag_clause = f" Its {bot_driver_str} is its most significant drag."
    else:
        drag_clause = ""

    band_word = {"STRONG": "strong", "REVIEW": "solid", "WEAK": "weak"}.get(band, "moderate")

    summary = (
        f"{symbol} scores {score_str} as a {fund_type} fund in {category}, "
        f"earning a {band_word} {band} rating. "
        f"Its score is driven primarily by its {top_driver_str}.{drag_clause}"
    )

    # Fund type note
    if fund_type == "Passive":
        fund_type_note = (
            f"As an index fund, {symbol} is scored on the Passive system, "
            f"which emphasizes cost efficiency (40% weight on expense ratio) and "
            f"tracking accuracy (30% combined across tracking error horizons). "
            f"Manager skill metrics like information ratio and Sortino are not used."
        )
    else:
        fund_type_note = (
            f"As an actively managed fund, {symbol} is scored on the Active system, "
            f"which rewards skill-based metrics: expense ratio (25%), information ratio "
            f"(20% combined), Sortino ratio (20% combined), downside protection (10% combined), "
            f"and upside/downside capture. Cost discipline still matters substantially."
        )

    return {
        "symbol": symbol,
        "name": name,
        "fund_type": fund_type,
        "category": category,
        "score": score,
        "band": band,
        "summary": summary,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "data_coverage": {
            "pct": coverage_pct,
            "metrics_with_data": n_with_data,
            "total_metrics": total_metrics,
            "missing": missing_keys,
        },
        "fund_type_note": fund_type_note,
        "breakdown": {k: v for k, v in breakdown.items()},
    }



def explain_score_difference(
    df_2023: pd.DataFrame,
    df_2025: pd.DataFrame,
    symbol: str,
) -> dict:
    """
    Compare the same fund's score between the 2023 Combined System and the 2025 Split System.
    Returns a detailed narrative explaining what changed and why.

    Parameters
    ----------
    df_2023 : DataFrame from scores_2023.csv (has Score_2023 column)
    df_2025 : scored DataFrame from load_and_score() (has Score_Final, Fund_Type)
    symbol  : ticker symbol to look up
    """
    sym_col = CSV_COLUMNS["symbol"]
    name_col = CSV_COLUMNS["name"]

    # ---- Locate fund in each dataset ----
    row_2023 = df_2023[df_2023["Symbol"] == symbol]
    row_2025 = df_2025[df_2025[sym_col] == symbol]

    if row_2023.empty and row_2025.empty:
        return {"error": f"Symbol '{symbol}' not found in either dataset."}

    score_2023 = float(row_2023.iloc[0]["Score_2023"]) if not row_2023.empty else None
    score_2025 = float(row_2025.iloc[0]["Score_Final"]) if not row_2025.empty else None
    fund_type_2025 = row_2025.iloc[0].get("Fund_Type", "Unknown") if not row_2025.empty else "Unknown"

    # Name from whichever dataset has it
    if not row_2025.empty:
        name = row_2025.iloc[0].get(name_col, symbol)
    elif not row_2023.empty:
        name = row_2023.iloc[0].get("Name", symbol)
    else:
        name = symbol

    s2023_str = f"{score_2023:.1f}" if score_2023 is not None else "N/A"
    s2025_str = f"{score_2025:.1f}" if score_2025 is not None else "N/A"

    # ---- Score change narrative ----
    if score_2023 is not None and score_2025 is not None:
        delta = score_2025 - score_2023
        direction_word = "improved" if delta > 0 else "declined"
        delta_str = f"{abs(delta):.1f}"
        system_label_2025 = f"2025 ({fund_type_2025} System)"
        header = (
            f"{symbol} scored {s2023_str} in the 2023 Combined System "
            f"and {s2025_str} in the {system_label_2025}."
        )
        change_summary = (
            f"The {delta_str}-point {direction_word} reflects a combination of "
            f"methodology changes and shifts in the fund's underlying metrics."
        )
    else:
        header = f"{symbol} ({name}): 2023 score = {s2023_str}, 2025 score = {s2025_str}."
        change_summary = ""
        delta = None

    # ---- Methodology difference explanation ----
    methodology_note = (
        "The 2023 system scored all funds (passive and active) together using 15 metrics. "
        "It valued alpha (22% combined weight for 5Y+10Y), manager tenure (6% combined), "
        "and total AUM (1.5%) — none of which exist in the 2025 system. "
        f"The 2025 {fund_type_2025} system instead uses "
    )
    if fund_type_2025 == "Active":
        methodology_note += (
            "Information Ratio (20% combined weight across 3Y/5Y/10Y) and Sortino Ratio "
            "(20% combined) as its core skill metrics, with expense ratio weighted at 25% "
            "(vs 5% in 2023). Alpha, manager tenure, and total AUM were removed entirely."
        )
    elif fund_type_2025 == "Passive":
        methodology_note += (
            "expense ratio as its dominant metric (40% weight), tracking error (30% combined "
            "across 3Y/5Y/10Y), and R-squared (5%). Alpha, manager tenure, and total AUM "
            "were removed entirely. Information ratio and Sortino ratio are not used for passive funds."
        )
    else:
        methodology_note += (
            "different metrics and weights depending on fund type. "
            "Alpha, manager tenure, and total AUM were removed."
        )

    # ---- 2023-only metric contributions ----
    metrics_2023_only = []
    if not row_2023.empty:
        r23 = row_2023.iloc[0]

        # Alpha contribution
        alpha_5y = r23.get("Alpha (vs Category) (5Y)")
        alpha_10y = r23.get("Alpha (vs Category) (10Y)")
        if pd.notna(alpha_5y) or pd.notna(alpha_10y):
            # Estimate percentile from the full 2023 dataset
            alpha_contrib_pts = 0.0
            alpha_notes = []
            for col_name, weight in [("Alpha (vs Category) (5Y)", 11), ("Alpha (vs Category) (10Y)", 11)]:
                val = r23.get(col_name)
                if pd.notna(val):
                    cat = r23.get("Category Name", "")
                    cat_peers = df_2023[df_2023["Category Name"] == cat][col_name].dropna()
                    if len(cat_peers) > 0:
                        pct = (cat_peers <= val).sum() / len(cat_peers)
                        contrib = pct * weight
                        alpha_contrib_pts += contrib
                        period = "5Y" if "5Y" in col_name else "10Y"
                        alpha_notes.append(
                            f"Alpha ({period}) of {val:.2f} ranks in the {round(pct*100)}th percentile "
                            f"(~{contrib:.1f} pts of {weight} max)"
                        )
            metrics_2023_only.append({
                "metric": "Alpha (5Y + 10Y)",
                "weight_2023": 22,
                "weight_2025": 0,
                "contribution_2023": round(alpha_contrib_pts, 1),
                "note": (
                    f"Alpha contributed approximately {alpha_contrib_pts:.1f} points in 2023 "
                    f"({'; '.join(alpha_notes)}). "
                    f"This metric was removed in the 2025 system — the 2025 active system "
                    f"uses Information Ratio instead, which measures consistency of excess returns "
                    f"relative to the benchmark on a risk-adjusted basis."
                ),
            })

        # Manager tenure
        med_ten = r23.get("Median Manager Tenure")
        avg_ten = r23.get("Average Manager Tenure")
        if pd.notna(med_ten) or pd.notna(avg_ten):
            ten_contrib_pts = 0.0
            ten_notes = []
            for col_name, weight in [("Median Manager Tenure", 3), ("Average Manager Tenure", 3)]:
                val = r23.get(col_name)
                if pd.notna(val):
                    cat = r23.get("Category Name", "")
                    cat_peers = df_2023[df_2023["Category Name"] == cat][col_name].dropna()
                    if len(cat_peers) > 0:
                        pct = (cat_peers <= val).sum() / len(cat_peers)
                        contrib = pct * weight
                        ten_contrib_pts += contrib
                        label = "Median" if "Median" in col_name else "Average"
                        ten_notes.append(
                            f"{label} tenure of {val:.1f} yrs → {round(pct*100)}th percentile "
                            f"(~{contrib:.1f} pts)"
                        )
            metrics_2023_only.append({
                "metric": "Manager Tenure (Median + Average)",
                "weight_2023": 6,
                "weight_2025": 0,
                "contribution_2023": round(ten_contrib_pts, 1),
                "note": (
                    f"Manager tenure contributed approximately {ten_contrib_pts:.1f} points in 2023 "
                    f"({'; '.join(ten_notes)}). "
                    f"This metric was removed in the 2025 system — research has not consistently "
                    f"supported tenure as a predictor of forward returns."
                ),
            })

    # ---- 2025-only metric contributions ----
    metrics_2025_only = []
    if not row_2025.empty and fund_type_2025 == "Active":
        r25 = row_2025.iloc[0]
        cat_2025 = r25.get(CSV_COLUMNS["category"], "")
        cat_df_2025 = df_2025[df_2025[CSV_COLUMNS["category"]] == cat_2025]

        # Information Ratio (3Y + 5Y + 10Y = 20 pts total)
        ir_contrib = 0.0
        ir_notes = []
        for key, weight in [("info_ratio_3y", 10), ("info_ratio_5y", 6), ("info_ratio_10y", 4)]:
            col = CSV_COLUMNS.get(key)
            val = r25.get(col) if col else None
            if val is not None and pd.notna(val):
                peers = cat_df_2025[col].dropna()
                if len(peers) > 0:
                    pct = (peers <= val).sum() / len(peers)
                    contrib = pct * weight
                    ir_contrib += contrib
                    period = key.split("_")[-1].upper()
                    ir_notes.append(
                        f"IR ({period}) {val:.2f} → {round(pct*100)}th pctile (~{contrib:.1f} pts)"
                    )
        if ir_contrib > 0 or ir_notes:
            metrics_2025_only.append({
                "metric": "Information Ratio (3Y + 5Y + 10Y)",
                "weight_2023": 0,
                "weight_2025": 20,
                "contribution_2025": round(ir_contrib, 1),
                "note": (
                    f"Information Ratio contributes up to 20 points in the 2025 active system "
                    f"({'; '.join(ir_notes) if ir_notes else 'data unavailable'}). "
                    f"This metric didn't exist in the 2023 system. It measures how consistently "
                    f"the fund delivers excess returns relative to its benchmark."
                ),
            })

        # Sortino Ratio (3Y + 5Y + 10Y = 20 pts total)
        so_contrib = 0.0
        so_notes = []
        for key, weight in [("sortino_3y", 10), ("sortino_5y", 6), ("sortino_10y", 4)]:
            col = CSV_COLUMNS.get(key)
            val = r25.get(col) if col else None
            if val is not None and pd.notna(val):
                peers = cat_df_2025[col].dropna()
                if len(peers) > 0:
                    pct = (peers <= val).sum() / len(peers)
                    contrib = pct * weight
                    so_contrib += contrib
                    period = key.split("_")[-1].upper()
                    so_notes.append(
                        f"Sortino ({period}) {val:.2f} → {round(pct*100)}th pctile (~{contrib:.1f} pts)"
                    )
        if so_contrib > 0 or so_notes:
            metrics_2025_only.append({
                "metric": "Sortino Ratio (3Y + 5Y + 10Y)",
                "weight_2023": 0,
                "weight_2025": 20,
                "contribution_2025": round(so_contrib, 1),
                "note": (
                    f"Sortino Ratio contributes up to 20 points in the 2025 active system "
                    f"({'; '.join(so_notes) if so_notes else 'data unavailable'}). "
                    f"This metric didn't exist in the 2023 system. It measures risk-adjusted "
                    f"returns penalizing only downside volatility."
                ),
            })

    # ---- Expense ratio comparison ----
    expense_note = None
    if not row_2023.empty and not row_2025.empty:
        er_2023 = row_2023.iloc[0].get("Annual Report Expense Ratio")
        er_col_2025 = CSV_COLUMNS.get("expense_ratio")
        er_2025 = row_2025.iloc[0].get(er_col_2025) if er_col_2025 else None

        if er_2023 is not None and pd.notna(er_2023):
            er_pct = er_2023 * 100 if er_2023 < 1 else er_2023  # handle if stored as decimal or percent
            # Normalize: if > 1 it's already in percent
            if er_2023 >= 1:
                er_display = f"{er_2023:.2f}%"
            else:
                er_display = f"{er_2023*100:.3f}%"

            old_weight = 5
            new_weight = 25 if fund_type_2025 == "Active" else 40
            expense_note = (
                f"Expense ratio weight increased from {old_weight}% (2023) to {new_weight}% (2025 {fund_type_2025}). "
                f"The fund's expense ratio ({er_display}) has a much larger impact on the 2025 score."
            )

    # ---- Shared metrics comparison ----
    shared_metrics = []
    if not row_2023.empty and not row_2025.empty:
        r23 = row_2023.iloc[0]
        r25 = row_2025.iloc[0]
        cat_2023 = r23.get("Category Name", "")
        cat_2025 = r25.get(CSV_COLUMNS["category"], "")

        # Drawdown overlap
        for col_23, col_25, label in [
            ("Max Drawdown (5Y)", CSV_COLUMNS.get("max_drawdown_5y"), "Max Drawdown (5Y)"),
            ("Max Drawdown (10Y)", CSV_COLUMNS.get("max_drawdown_10y"), "Max Drawdown (10Y)"),
        ]:
            if col_25 is None:
                continue
            v23 = r23.get(col_23)
            v25 = r25.get(col_25)
            if v23 is not None and v25 is not None and pd.notna(v23) and pd.notna(v25):
                # Percentile in 2023
                peers_23 = df_2023[df_2023["Category Name"] == cat_2023][col_23].dropna()
                pct_23 = (peers_23 >= v23).sum() / len(peers_23) * 100 if len(peers_23) > 0 else None
                # Percentile in 2025
                peers_25 = df_2025[df_2025[CSV_COLUMNS["category"]] == cat_2025][col_25].dropna()
                pct_25 = (peers_25 >= v25).sum() / len(peers_25) * 100 if len(peers_25) > 0 else None
                shared_metrics.append({
                    "metric": label,
                    "value_2023": round(float(v23), 4),
                    "value_2025": round(float(v25), 4),
                    "percentile_2023": round(pct_23, 1) if pct_23 is not None else None,
                    "percentile_2025": round(pct_25, 1) if pct_25 is not None else None,
                })

        # Upside/Downside capture overlap
        for col_23, col_25, label, direction in [
            ("Upside (5Y)", CSV_COLUMNS.get("upside_5y"), "Upside Capture (5Y)", "higher"),
            ("Upside (10Y)", CSV_COLUMNS.get("upside_10y"), "Upside Capture (10Y)", "higher"),
            ("Downside (5Y)", CSV_COLUMNS.get("downside_5y"), "Downside Capture (5Y)", "lower"),
            ("Downside (10Y)", CSV_COLUMNS.get("downside_10y"), "Downside Capture (10Y)", "lower"),
        ]:
            if col_25 is None:
                continue
            v23 = r23.get(col_23)
            v25 = r25.get(col_25)
            if v23 is not None and v25 is not None and pd.notna(v23) and pd.notna(v25):
                peers_23 = df_2023[df_2023["Category Name"] == cat_2023][col_23].dropna()
                if direction == "higher":
                    pct_23 = (peers_23 <= v23).sum() / len(peers_23) * 100 if len(peers_23) > 0 else None
                else:
                    pct_23 = (peers_23 >= v23).sum() / len(peers_23) * 100 if len(peers_23) > 0 else None
                peers_25 = df_2025[df_2025[CSV_COLUMNS["category"]] == cat_2025][col_25].dropna()
                if direction == "higher":
                    pct_25 = (peers_25 <= v25).sum() / len(peers_25) * 100 if len(peers_25) > 0 else None
                else:
                    pct_25 = (peers_25 >= v25).sum() / len(peers_25) * 100 if len(peers_25) > 0 else None
                shared_metrics.append({
                    "metric": label,
                    "value_2023": round(float(v23), 4),
                    "value_2025": round(float(v25), 4),
                    "percentile_2023": round(pct_23, 1) if pct_23 is not None else None,
                    "percentile_2025": round(pct_25, 1) if pct_25 is not None else None,
                })

    # ---- Net narrative ----
    net_narrative_parts = []
    if delta is not None:
        direction_label = "decline" if delta < 0 else "improvement"
        net_narrative_parts.append(
            f"The {abs(delta):.1f}-point {direction_label} from {s2023_str} to {s2025_str} "
            f"is primarily explained by:"
        )

    drivers = []
    # Alpha removal
    alpha_entry = next((m for m in metrics_2023_only if "Alpha" in m["metric"]), None)
    if alpha_entry and alpha_entry["contribution_2023"] > 0:
        drivers.append(
            f"The removal of alpha from the scoring system, which contributed "
            f"~{alpha_entry['contribution_2023']:.1f} points in 2023"
        )

    # Expense ratio reweighting
    if expense_note:
        drivers.append(expense_note)

    # IR and Sortino additions
    ir_entry = next((m for m in metrics_2025_only if "Information Ratio" in m["metric"]), None)
    so_entry = next((m for m in metrics_2025_only if "Sortino" in m["metric"]), None)
    if ir_entry or so_entry:
        ir_pts = ir_entry["contribution_2025"] if ir_entry else 0
        so_pts = so_entry["contribution_2025"] if so_entry else 0
        drivers.append(
            f"The addition of Information Ratio (~{ir_pts:.1f} pts earned) and Sortino Ratio "
            f"(~{so_pts:.1f} pts earned) — new metrics in the 2025 system that didn't exist in 2023"
        )

    # Tenure removal
    ten_entry = next((m for m in metrics_2023_only if "Tenure" in m["metric"]), None)
    if ten_entry and ten_entry["contribution_2023"] > 0:
        drivers.append(
            f"The removal of manager tenure, which had contributed "
            f"~{ten_entry['contribution_2023']:.1f} points in 2023"
        )

    net_narrative = " ".join(net_narrative_parts)
    if drivers:
        for i, d in enumerate(drivers, 1):
            d_clean = d.rstrip(".")
            net_narrative += f"\n({i}) {d_clean}."

    return {
        "symbol": symbol,
        "name": name,
        "fund_type_2025": fund_type_2025,
        "score_2023": score_2023,
        "score_2025": score_2025,
        "delta": round(delta, 1) if delta is not None else None,
        # Alias fields for backward compatibility
        "score_earlier": score_2023,
        "score_current": score_2025,
        "header": header,
        "summary": header + (" " + change_summary if change_summary else ""),
        "methodology_note": methodology_note,
        "metrics_2023_only": metrics_2023_only,
        "metrics_2025_only": metrics_2025_only,
        "expense_note": expense_note,
        "shared_metrics": shared_metrics,
        "net_narrative": net_narrative,
        # Legacy fields
        "system_change_note": methodology_note,
        "likely_drivers": drivers,
        "metric_overlap": shared_metrics,
    }


def generate_category_narrative(scored_df: pd.DataFrame, category: str) -> str:
    """
    Returns a paragraph summarizing the category's scoring landscape.
    """
    cat_col = CSV_COLUMNS["category"]
    sym_col = CSV_COLUMNS["symbol"]

    cat_df = scored_df[scored_df[cat_col] == category]
    if cat_df.empty:
        return f"No funds found in category '{category}'."

    n_total = len(cat_df)
    n_passive = (cat_df["Fund_Type"] == "Passive").sum()
    n_active = (cat_df["Fund_Type"] == "Active").sum()

    scored_cat = cat_df[cat_df["Score_Final"].notna()]
    if scored_cat.empty:
        return f"{category} contains {n_total} funds but none could be scored with available data."

    avg_score = scored_cat["Score_Final"].mean()
    n_strong = (scored_cat["Score_Band"] == "STRONG").sum()
    pct_strong = n_strong / len(scored_cat) * 100

    passive_df = scored_cat[scored_cat["Fund_Type"] == "Passive"]
    active_df = scored_cat[scored_cat["Fund_Type"] == "Active"]
    avg_passive = passive_df["Score_Final"].mean() if len(passive_df) > 0 else None
    avg_active = active_df["Score_Final"].mean() if len(active_df) > 0 else None

    top_fund = scored_cat.loc[scored_cat["Score_Final"].idxmax()]
    top_sym = top_fund[sym_col]
    top_score = top_fund["Score_Final"]

    bottom_fund = scored_cat.loc[scored_cat["Score_Final"].idxmin()]
    bot_sym = bottom_fund[sym_col]
    bot_score = bottom_fund["Score_Final"]

    # Type breakdown sentence
    type_breakdown = f"{n_passive} passive, {n_active} active" if n_passive > 0 and n_active > 0 \
        else (f"{n_passive} passive" if n_passive > 0 else f"{n_active} active")

    narrative = (
        f"{category} contains {n_total} funds ({type_breakdown}). "
        f"The category average score is {avg_score:.1f}, with {pct_strong:.0f}% scoring STRONG. "
    )

    if avg_passive is not None and avg_active is not None:
        passive_advantage = avg_passive - avg_active
        if passive_advantage > 3:
            narrative += (
                f"Passive funds in this category average {avg_passive:.1f} vs. "
                f"{avg_active:.1f} for active funds — passive vehicles benefit from "
                f"lower costs in a space where index investing captures most of the market beta. "
            )
        elif passive_advantage < -3:
            narrative += (
                f"Active funds in this category average {avg_active:.1f} vs. "
                f"{avg_passive:.1f} for passive — suggesting skilled managers add value "
                f"beyond what index exposure provides. "
            )
        else:
            narrative += (
                f"Passive ({avg_passive:.1f} avg) and active ({avg_active:.1f} avg) funds "
                f"score similarly in this category. "
            )
    elif avg_passive is not None:
        narrative += f"All scoreable funds in this category are passive, averaging {avg_passive:.1f}. "
    elif avg_active is not None:
        narrative += f"All scoreable funds in this category are actively managed, averaging {avg_active:.1f}. "

    narrative += (
        f"The top performer is {top_sym} ({top_score:.1f}). "
        f"The lowest-scoring fund is {bot_sym} ({bot_score:.1f})."
    )

    return narrative
