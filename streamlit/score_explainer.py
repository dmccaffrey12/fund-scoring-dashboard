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
    scored_df_2023: pd.DataFrame,
    scored_df_2025: pd.DataFrame,
    symbol: str,
) -> dict:
    """
    Compare the same fund's score across two different scoring system snapshots.
    Returns a narrative explaining the difference.
    """
    sym_col = CSV_COLUMNS["symbol"]
    name_col = CSV_COLUMNS["name"]

    row_2023 = scored_df_2023[scored_df_2023[sym_col] == symbol]
    row_2025 = scored_df_2025[scored_df_2025[sym_col] == symbol]

    if row_2023.empty and row_2025.empty:
        return {"error": f"Symbol '{symbol}' not found in either dataset."}

    score_2023 = row_2023.iloc[0].get("Score_Final") if not row_2023.empty else None
    score_2025 = row_2025.iloc[0].get("Score_Final") if not row_2025.empty else None
    fund_type_2025 = row_2025.iloc[0].get("Fund_Type", "Unknown") if not row_2025.empty else "Unknown"
    name = row_2025.iloc[0].get(name_col, symbol) if not row_2025.empty else symbol

    s2023_str = f"{score_2023:.1f}" if score_2023 is not None and pd.notna(score_2023) else "N/A"
    s2025_str = f"{score_2025:.1f}" if score_2025 is not None and pd.notna(score_2025) else "N/A"

    if score_2023 is not None and score_2025 is not None and pd.notna(score_2023) and pd.notna(score_2025):
        delta = score_2025 - score_2023
        direction = "improved" if delta > 0 else "declined"
        delta_str = f"{abs(delta):.1f}"
        summary = (
            f"{symbol} scored {s2023_str} in the earlier dataset vs. {s2025_str} in the current "
            f"dataset ({fund_type_2025}). The {delta_str}-point {direction} may reflect both "
            f"changes in fund fundamentals and differences in the scoring methodology."
        )
    else:
        summary = (
            f"{symbol} ({name}): Earlier score = {s2023_str}, Current score = {s2025_str}."
        )

    system_change_note = (
        "Important: these two scores were produced by different scoring systems. "
        "The earlier system may have used different metrics, weights, and peer groups. "
        "The current 2025 system weights expense ratio at 25% (active) or 40% (passive), "
        "and emphasizes information ratio and Sortino ratio for active funds. "
        "Score differences may reflect methodology changes rather than fund deterioration or improvement."
    )

    # Identify metric overlap between the two datasets
    active_metric_keys = {k for k, _, _ in ACTIVE_METRICS}
    passive_metric_keys = {k for k, _, _ in PASSIVE_METRICS}
    all_metric_keys = active_metric_keys | passive_metric_keys

    metric_overlap = []
    if not row_2023.empty and not row_2025.empty:
        r23 = row_2023.iloc[0]
        r25 = row_2025.iloc[0]
        for key in sorted(all_metric_keys):
            col = CSV_COLUMNS.get(key, key)
            v23 = r23.get(col) if col in scored_df_2023.columns else None
            v25 = r25.get(col) if col in scored_df_2025.columns else None
            if v23 is not None and v25 is not None and pd.notna(v23) and pd.notna(v25):
                change = v25 - v23
                metric_overlap.append({
                    "metric": METRIC_LABELS.get(key, key),
                    "earlier_value": round(float(v23), 4),
                    "current_value": round(float(v25), 4),
                    "change": round(float(change), 4),
                })

    # Build likely drivers narrative
    likely_drivers = [
        "The scoring methodology differs between the two datasets — different metrics may be included or excluded.",
        "Expense ratio weighting is substantial (25-40%) in the current system; any fee changes will have outsized impact.",
        "Information ratio and Sortino ratio are core to the current active system — periods of underperformance relative to benchmark will show up strongly.",
        "If the fund's peer group composition changed (category reassignment), percentile rankings would shift even if raw metrics stayed the same.",
    ]

    return {
        "symbol": symbol,
        "name": name,
        "score_earlier": score_2023,
        "score_current": score_2025,
        "summary": summary,
        "system_change_note": system_change_note,
        "likely_drivers": likely_drivers,
        "metric_overlap": metric_overlap,
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
