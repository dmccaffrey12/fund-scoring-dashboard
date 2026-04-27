"""
Benchmark Fit / Portfolio Alignment
===================================
Compute weighted stylebox + sector exposures for the model and a benchmark,
the resulting active drift, and replacement-simulation deltas.

Product premise:
    The 100/0 equity model is the canonical equity sleeve. Lower-risk
    models are scaled versions of the same sleeve, so we do not maintain
    a separate benchmark per risk model — the same equity-sleeve drift
    answers the question for every model that owns the sleeve.

Static default benchmark: a 100/0 equity blend approximated by:
    SPYM 58%, EFA 24%, SPMD 6%, SPSM 6%, EEM 6%

Public surface:

    DEFAULT_BENCHMARK_WEIGHTS
    weighted_exposure(holdings_weights, exposures) -> dict
    benchmark_exposure(weights, exposures) -> dict
    drift_metrics(actual, target) -> dict (per-bucket active + max + total)
    fit_label(metrics) -> str
    simulate_replacements(...) -> pd.DataFrame
    build_benchmark_fit_artifacts(...) -> dict (multiple DataFrames)
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

import numpy as np
import pandas as pd

from exposure_intake import (
    CLEAN_COLUMNS,
    SECTOR_BUCKETS,
    STYLEBOX_BUCKETS,
)


# Static 100/0 equity benchmark — chosen by the investment team to
# approximate a globally-diversified equity sleeve. Update via
# ``benchmark_weights_from_mapping`` or by editing this dict.
DEFAULT_BENCHMARK_WEIGHTS: Dict[str, float] = {
    "SPYM": 0.58,
    "EFA":  0.24,
    "SPMD": 0.06,
    "SPSM": 0.06,
    "EEM":  0.06,
}


ALL_BUCKETS: List[str] = STYLEBOX_BUCKETS + SECTOR_BUCKETS


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _norm_weights(weights: Mapping[str, float]) -> Dict[str, float]:
    """Strip blanks, upper-case, drop zero/NaN, leave totals untouched."""
    out: Dict[str, float] = {}
    for sym, w in weights.items():
        s = str(sym).strip().upper()
        if not s:
            continue
        try:
            v = float(w)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(v) or v == 0.0:
            continue
        out[s] = out.get(s, 0.0) + v
    return out


def _exposure_lookup(exposures: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Build {SYMBOL: {bucket: exposure_float}} from a clean exposure frame."""
    if exposures is None or exposures.empty:
        return {}
    df = exposures.copy()
    df["Symbol"] = df["Symbol"].astype(str).str.strip().str.upper()
    out: Dict[str, Dict[str, float]] = {}
    for _, row in df.iterrows():
        sym = row["Symbol"]
        if not sym:
            continue
        rec: Dict[str, float] = {}
        for col in ALL_BUCKETS:
            v = row.get(col)
            if pd.isna(v):
                continue
            rec[col] = float(v)
        out[sym] = rec
    return out


# ---------------------------------------------------------------------------
# Weighted exposures
# ---------------------------------------------------------------------------

def weighted_exposure(
    holdings_weights: Mapping[str, float],
    exposures: pd.DataFrame,
) -> Dict[str, float]:
    """Return {bucket: weighted_exposure} for an arbitrary holdings dict.

    Missing tickers (no exposure row available) are reported under the
    ``_missing`` key as a sorted list. Weights are not renormalized — the
    caller is responsible for sleeve-level scaling.
    """
    weights = _norm_weights(holdings_weights)
    lookup = _exposure_lookup(exposures)

    totals: Dict[str, float] = {b: 0.0 for b in ALL_BUCKETS}
    missing: List[str] = []
    matched_weight = 0.0
    for sym, w in weights.items():
        rec = lookup.get(sym)
        if rec is None:
            missing.append(sym)
            continue
        matched_weight += w
        for b in ALL_BUCKETS:
            v = rec.get(b)
            if v is not None and np.isfinite(v):
                totals[b] += w * v

    out: Dict[str, Any] = dict(totals)
    out["_matched_weight"] = matched_weight
    out["_missing"] = sorted(missing)
    return out


def benchmark_exposure(
    benchmark_weights: Mapping[str, float],
    exposures: pd.DataFrame,
) -> Dict[str, float]:
    """Same as ``weighted_exposure`` but intended for the benchmark side.
    Kept as a separate name so callers stay self-documenting.
    """
    return weighted_exposure(benchmark_weights, exposures)


# ---------------------------------------------------------------------------
# Drift / fit
# ---------------------------------------------------------------------------

def _bucket_split(metrics: Dict[str, float]) -> Dict[str, float]:
    """Return total/max drift split into stylebox vs sector parts."""
    sb_abs = sum(abs(metrics.get(b, 0.0)) for b in STYLEBOX_BUCKETS)
    sec_abs = sum(abs(metrics.get(b, 0.0)) for b in SECTOR_BUCKETS)
    sb_max = max((abs(metrics.get(b, 0.0)) for b in STYLEBOX_BUCKETS),
                 default=0.0)
    sec_max = max((abs(metrics.get(b, 0.0)) for b in SECTOR_BUCKETS),
                  default=0.0)
    return {
        "stylebox_total_abs_drift": sb_abs,
        "sector_total_abs_drift": sec_abs,
        "stylebox_max_abs_drift": sb_max,
        "sector_max_abs_drift": sec_max,
    }


def drift_metrics(
    actual: Mapping[str, float],
    target: Mapping[str, float],
) -> Dict[str, Any]:
    """Active weights = actual − target. Returns per-bucket active values
    plus aggregate stats (total/max abs drift, stylebox/sector split).
    """
    active: Dict[str, float] = {}
    for b in ALL_BUCKETS:
        a = float(actual.get(b, 0.0) or 0.0)
        t = float(target.get(b, 0.0) or 0.0)
        active[b] = a - t

    total_abs = sum(abs(v) for v in active.values())
    max_abs = max((abs(v) for v in active.values()), default=0.0)
    max_bucket = None
    for b in ALL_BUCKETS:
        if abs(active[b]) == max_abs and max_abs > 0:
            max_bucket = b
            break

    out: Dict[str, Any] = {
        "active": active,
        "total_abs_drift": total_abs,
        "max_abs_drift": max_abs,
        "max_drift_bucket": max_bucket,
    }
    out.update(_bucket_split(active))
    return out


# Fit thresholds chosen so a Strong Fit corresponds to a portfolio that
# tracks the static 100/0 benchmark closely on both stylebox and sector
# axes; Drift Risk catches sleeves that are meaningfully off in any one
# bucket. Tunable — exposed as constants for easy adjustment.
STRONG_TOTAL_DRIFT = 0.20
STRONG_MAX_DRIFT = 0.06
ACCEPTABLE_TOTAL_DRIFT = 0.40
ACCEPTABLE_MAX_DRIFT = 0.10


def fit_label(metrics: Mapping[str, Any]) -> str:
    """Return one of ``"Strong Fit"``, ``"Acceptable"``, ``"Drift Risk"``.

    Strong Fit:    total ≤ STRONG_TOTAL_DRIFT and max ≤ STRONG_MAX_DRIFT
    Acceptable:    total ≤ ACCEPTABLE_TOTAL_DRIFT and max ≤ ACCEPTABLE_MAX_DRIFT
    Drift Risk:    otherwise
    """
    total = float(metrics.get("total_abs_drift", 0.0) or 0.0)
    max_d = float(metrics.get("max_abs_drift", 0.0) or 0.0)
    if total <= STRONG_TOTAL_DRIFT and max_d <= STRONG_MAX_DRIFT:
        return "Strong Fit"
    if total <= ACCEPTABLE_TOTAL_DRIFT and max_d <= ACCEPTABLE_MAX_DRIFT:
        return "Acceptable"
    return "Drift Risk"


# ---------------------------------------------------------------------------
# Replacement simulation
# ---------------------------------------------------------------------------

def _holdings_dict_from_frame(
    holdings: pd.DataFrame,
    *,
    symbol_col: str = "Symbol",
    weight_col: str = "Target_Weight",
) -> Dict[str, float]:
    if holdings is None or holdings.empty:
        return {}
    out: Dict[str, float] = {}
    for _, row in holdings.iterrows():
        sym = str(row.get(symbol_col, "")).strip().upper()
        if not sym:
            continue
        try:
            w = float(row.get(weight_col, 0.0))
        except (TypeError, ValueError):
            continue
        if not np.isfinite(w):
            continue
        out[sym] = out.get(sym, 0.0) + w
    return out


def simulate_replacements(
    *,
    model_holdings: pd.DataFrame,
    model_exposures: pd.DataFrame,
    candidate_exposures: pd.DataFrame,
    benchmark_weights: Mapping[str, float],
    benchmark_exposures: pd.DataFrame,
    target_symbol: str,
    candidate_symbols: Optional[List[str]] = None,
    symbol_col: str = "Symbol",
    weight_col: str = "Target_Weight",
) -> pd.DataFrame:
    """Simulate replacing ``target_symbol`` at its model weight with each
    candidate. Returns one row per candidate with drift before/after.

    If ``model_exposures`` does not contain a candidate's row, the
    candidate's exposure is sourced from ``candidate_exposures``.

    The "before" baseline is computed once (current model vs benchmark);
    "after" is computed by removing the target's contribution and adding
    the candidate's exposure × the target's weight.
    """
    target = str(target_symbol).strip().upper()
    holdings = _holdings_dict_from_frame(
        model_holdings, symbol_col=symbol_col, weight_col=weight_col,
    )
    if target not in holdings:
        return pd.DataFrame()

    target_weight = holdings[target]

    # Baseline current-model exposures — uses model_exposures as the
    # primary source, falls back to candidate_exposures for any holding
    # not in model_exposures.
    fallback = _exposure_lookup(candidate_exposures)
    primary = _exposure_lookup(model_exposures)
    merged_lookup: Dict[str, Dict[str, float]] = {**fallback, **primary}

    # Build a synthetic exposure DataFrame for the current-model run that
    # contains every holding the model owns, so weighted_exposure misses
    # nothing.
    rows = []
    for sym in holdings:
        rec = merged_lookup.get(sym)
        if rec is None:
            continue
        row = {"Symbol": sym, "Name": ""}
        for b in ALL_BUCKETS:
            row[b] = rec.get(b, np.nan)
        rows.append(row)
    holdings_df = pd.DataFrame(rows, columns=CLEAN_COLUMNS)

    actual_now = weighted_exposure(holdings, holdings_df)
    bench_now = benchmark_exposure(benchmark_weights, benchmark_exposures)
    before = drift_metrics(actual_now, bench_now)

    cand_lookup = _exposure_lookup(candidate_exposures)
    if candidate_symbols is None:
        candidate_symbols = sorted(cand_lookup.keys())
    candidate_symbols = [
        str(s).strip().upper() for s in candidate_symbols
        if str(s).strip().upper() and str(s).strip().upper() != target
    ]

    # Pre-compute the "without target" baseline so we don't repeat it.
    target_rec = merged_lookup.get(target, {})
    actual_no_target: Dict[str, float] = {
        b: actual_now.get(b, 0.0) - target_weight * target_rec.get(b, 0.0)
        for b in ALL_BUCKETS
    }

    out_rows: List[Dict[str, Any]] = []
    for cand in candidate_symbols:
        rec = cand_lookup.get(cand) or merged_lookup.get(cand)
        if rec is None:
            continue
        actual_after: Dict[str, float] = {
            b: actual_no_target.get(b, 0.0) + target_weight * rec.get(b, 0.0)
            for b in ALL_BUCKETS
        }
        after = drift_metrics(actual_after, bench_now)
        label = fit_label(after)

        row: Dict[str, Any] = {
            "Candidate_Symbol": cand,
            "Replacement_Weight": target_weight,
            "Total_Abs_Drift_Before": before["total_abs_drift"],
            "Total_Abs_Drift_After": after["total_abs_drift"],
            "Total_Abs_Drift_Change": (
                after["total_abs_drift"] - before["total_abs_drift"]
            ),
            "Max_Abs_Drift_Before": before["max_abs_drift"],
            "Max_Abs_Drift_After": after["max_abs_drift"],
            "Max_Drift_Bucket_After": after["max_drift_bucket"],
            "Stylebox_Drift_Before": before["stylebox_total_abs_drift"],
            "Stylebox_Drift_After": after["stylebox_total_abs_drift"],
            "Sector_Drift_Before": before["sector_total_abs_drift"],
            "Sector_Drift_After": after["sector_total_abs_drift"],
            "Fit_Label": label,
        }
        out_rows.append(row)

    out = pd.DataFrame(out_rows)
    if out.empty:
        return out
    out = out.sort_values(
        ["Total_Abs_Drift_After", "Max_Abs_Drift_After", "Candidate_Symbol"],
        ascending=[True, True, True],
        kind="stable",
    ).reset_index(drop=True)
    out.insert(0, "Fit_Rank", range(1, len(out) + 1))
    return out


# ---------------------------------------------------------------------------
# Artifact builder
# ---------------------------------------------------------------------------

def _exposures_to_active_frame(
    actual: Mapping[str, float],
    target: Mapping[str, float],
    metrics: Mapping[str, Any],
) -> pd.DataFrame:
    rows = []
    active = metrics.get("active", {})
    for b in ALL_BUCKETS:
        rows.append({
            "Bucket_Type": "Stylebox" if b in STYLEBOX_BUCKETS else "Sector",
            "Bucket": b,
            "Model_Exposure": float(actual.get(b, 0.0) or 0.0),
            "Benchmark_Exposure": float(target.get(b, 0.0) or 0.0),
            "Active_Weight": float(active.get(b, 0.0) or 0.0),
        })
    return pd.DataFrame(rows)


def build_benchmark_fit_artifacts(
    *,
    model_holdings: pd.DataFrame,
    model_exposures: pd.DataFrame,
    benchmark_exposures: pd.DataFrame,
    benchmark_weights: Mapping[str, float],
    candidate_exposures: Optional[pd.DataFrame] = None,
    target_symbol: Optional[str] = None,
    candidate_symbols: Optional[List[str]] = None,
    symbol_col: str = "Symbol",
    weight_col: str = "Target_Weight",
) -> Dict[str, Any]:
    """Produce all benchmark-fit DataFrames needed by the workbench.

    Returns a dict with:
        model_actual:          Mapping {bucket: weighted}
        bench_actual:          Mapping {bucket: weighted}
        baseline_metrics:      drift_metrics output for the current model
        baseline_fit_label:    "Strong Fit" / "Acceptable" / "Drift Risk"
        current_vs_benchmark:  long-form DataFrame (one row per bucket)
        replacement_table:     simulate_replacements output (may be empty)
        replacement_delta:     long-form best-candidate active drift table
                                (only when target_symbol is supplied and a
                                top-1 candidate exists)
        missing_holdings:      list of model holdings missing exposure rows
        missing_benchmark:     list of benchmark constituents missing rows
    """
    holdings = _holdings_dict_from_frame(
        model_holdings, symbol_col=symbol_col, weight_col=weight_col,
    )

    # Allow benchmark constituents to source exposures from model_exposures
    # too — that's how the workspace files are wired (the model export
    # includes SPYM/SPSM, while the benchmark export includes EFA/EEM/SPMD).
    fallback = _exposure_lookup(model_exposures)
    primary = _exposure_lookup(benchmark_exposures)
    merged_lookup: Dict[str, Dict[str, float]] = {**fallback, **primary}
    bench_combined = pd.DataFrame(
        [
            {"Symbol": s, "Name": "",
             **{b: rec.get(b, np.nan) for b in ALL_BUCKETS}}
            for s, rec in merged_lookup.items()
        ],
        columns=CLEAN_COLUMNS,
    )

    model_actual = weighted_exposure(holdings, model_exposures)
    bench_actual = benchmark_exposure(benchmark_weights, bench_combined)

    baseline = drift_metrics(model_actual, bench_actual)
    baseline_label = fit_label(baseline)

    current_vs_bench = _exposures_to_active_frame(
        model_actual, bench_actual, baseline,
    )

    replacement_table = pd.DataFrame()
    replacement_delta = pd.DataFrame()
    if target_symbol and candidate_exposures is not None:
        replacement_table = simulate_replacements(
            model_holdings=model_holdings,
            model_exposures=model_exposures,
            candidate_exposures=candidate_exposures,
            benchmark_weights=benchmark_weights,
            benchmark_exposures=bench_combined,
            target_symbol=target_symbol,
            candidate_symbols=candidate_symbols,
            symbol_col=symbol_col,
            weight_col=weight_col,
        )

        if not replacement_table.empty:
            top = replacement_table.iloc[0]
            top_sym = top["Candidate_Symbol"]

            # Re-run the after-state for the top candidate so we can emit
            # the per-bucket active-drift detail.
            target_rec = merged_lookup.get(target_symbol.upper(), {})
            target_weight = holdings.get(target_symbol.upper(), 0.0)
            cand_lookup = _exposure_lookup(candidate_exposures)
            cand_rec = cand_lookup.get(top_sym, merged_lookup.get(top_sym, {}))
            after_actual = {
                b: model_actual.get(b, 0.0)
                   - target_weight * target_rec.get(b, 0.0)
                   + target_weight * cand_rec.get(b, 0.0)
                for b in ALL_BUCKETS
            }
            after_metrics = drift_metrics(after_actual, bench_actual)
            replacement_delta = _exposures_to_active_frame(
                after_actual, bench_actual, after_metrics,
            )
            replacement_delta.insert(0, "Candidate_Symbol", top_sym)

    return {
        "model_actual": model_actual,
        "bench_actual": bench_actual,
        "baseline_metrics": baseline,
        "baseline_fit_label": baseline_label,
        "current_vs_benchmark": current_vs_bench,
        "replacement_table": replacement_table,
        "replacement_delta": replacement_delta,
        "missing_holdings": list(model_actual.get("_missing", [])),
        "missing_benchmark": list(bench_actual.get("_missing", [])),
    }


def benchmark_weights_from_mapping(
    weights: Mapping[str, float],
) -> Dict[str, float]:
    """Public sanitizer for user-supplied benchmark weights."""
    return _norm_weights(weights)
