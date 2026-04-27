"""
Replacement Workbench
=====================
Focused one-off "if this single model holding isn't acceptable, what should
replace it?" tool.

This is deliberately narrower than the committee-wide monthly packet /
overlay build:

- The overlay (``model_holdings_overlay``) scans every holding in every
  model, flags weak links, and emits a packet-wide short list.
- The workbench answers a single research question — "I need to replace
  ticker X" — and produces a short, actionable same-category candidate
  list with both 2023 and 2025 scores visible side-by-side.

The workbench reuses the same substrate as the overlay:
    - archived dual-score tables (``run_archive``)
    - share-class alias reconciliation (``symbol_aliases``)
    - the ``model_holdings_scorecard`` already produced by the overlay, if
      present, so we can surface the current holding's profile exactly as
      the committee would see it.

Public API:
    WORKBENCH_SUBDIR
    ReplacementResult
    build_replacement_workbench(...)
    write_replacement(result, out_dir) -> Dict[str, str]
    load_replacement(out_dir) -> Optional[Dict[str, Any]]
    run_replacement_for_run(run, ticker, ...) -> ReplacementResult

CLI:
    python replacement_workbench.py build \
        --run-date 2026-04-30 \
        --ticker PRBLX \
        --top-n 10

Canonical artifact layout under the run archive:

    runs/<run-date>/replacement_workbench/<TICKER>/
        replacement_candidates.csv
        current_holding_profile.csv
        replacement_summary.json
        replacement_brief.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

import numpy as np
import pandas as pd

from symbol_aliases import (
    apply_aliases,
    load_default_aliases,
    resolve_symbol,
)


WORKBENCH_SUBDIR = "replacement_workbench"

CANDIDATES_NAME = "replacement_candidates.csv"
CURRENT_PROFILE_NAME = "current_holding_profile.csv"
SUMMARY_NAME = "replacement_summary.json"
BRIEF_NAME = "replacement_brief.md"

# Benchmark-fit artifact filenames. Written only when the caller supplies
# exposure data; absent files mean "fit layer not run for this ticker".
BENCHMARK_FIT_CANDIDATES_NAME = "benchmark_fit_candidates.csv"
CURRENT_VS_BENCHMARK_NAME = "current_vs_benchmark_exposure.csv"
REPLACEMENT_DELTA_NAME = "replacement_exposure_delta.csv"

DEFAULT_TOP_N = 10

CANDIDATE_COLUMNS: List[str] = [
    "Rank",
    "Symbol",
    "Name",
    "Category",
    "Fund_Type",
    "Score_2023_Final",
    "Score_2025_Final",
    "Rank_2023",
    "Rank_2025",
    "Consensus_Rank",
    "Score_Band_2023",
    "Score_Band_2025",
    "Quadrant",
    "Action_Flag",
    "Primary_Driver",
    "Already_Held",
    "Held_By_Models",
    "From_Uploaded_Universe",
    "Reason_Label",
]


# Candidate universe modes.
#   "auto"     — restrict to uploaded candidate exposures when one is provided,
#                otherwise fall back to the full scored universe (legacy).
#   "uploaded" — always restrict to the uploaded candidate exposure file.
#                Ignored (with a warning) if no candidate_exposures supplied.
#   "scored"   — never restrict; rank against the full scored universe like
#                the pre-fit-layer workbench did.
CANDIDATE_UNIVERSE_MODES = ("auto", "uploaded", "scored")

PROFILE_COLUMNS: List[str] = [
    "Symbol",
    "Scoring_Symbol",
    "Alias_Applied",
    "Name",
    "Category",
    "Fund_Type",
    "Score_2023_Final",
    "Score_2025_Final",
    "Score_Gap",
    "Rank_2023",
    "Rank_2025",
    "Consensus_Rank",
    "Score_Band_2023",
    "Score_Band_2025",
    "Quadrant",
    "Action_Flag",
    "Primary_Driver",
    "Data_Coverage_2023",
    "Data_Coverage_2025",
    "Model_Name",
    "Target_Weight_Pct",
    "Overlay_Action",
    "Scored_In_Universe",
]


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ReplacementResult:
    """Container for all artifacts produced by ``build_replacement_workbench``."""

    ticker: str
    resolved_ticker: str
    alias_applied: bool
    category: Optional[str]
    category_source: str  # "universe", "override", or "unknown"
    candidates: pd.DataFrame
    current_profile: pd.DataFrame
    summary: Dict[str, Any]
    brief_markdown: str
    held_symbols: List[str] = field(default_factory=list)
    benchmark_fit_candidates: pd.DataFrame = field(default_factory=pd.DataFrame)
    current_vs_benchmark: pd.DataFrame = field(default_factory=pd.DataFrame)
    replacement_delta: pd.DataFrame = field(default_factory=pd.DataFrame)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm(symbol: Any) -> str:
    if symbol is None:
        return ""
    if isinstance(symbol, float) and pd.isna(symbol):
        return ""
    return str(symbol).strip().upper()


def _ensure_string_symbol(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def _format_float(value: Any, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _format_int(value: Any) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    try:
        return f"{int(value)}"
    except (TypeError, ValueError):
        return str(value)


def _reason_label(row: pd.Series) -> str:
    """Short human-readable fit label preserving 2023/2025 disagreement."""
    b23 = row.get("Score_Band_2023")
    b25 = row.get("Score_Band_2025")
    if b23 == "STRONG" and b25 == "STRONG":
        return "Consensus strong — both systems agree"
    if b23 == "STRONG" and b25 in {"REVIEW", "WEAK"}:
        return "Performance-led — strong on 2023, softer on 2025"
    if b25 == "STRONG" and b23 in {"REVIEW", "WEAK"}:
        return "Quality-led — strong on 2025, weaker track record on 2023"
    if b23 == "REVIEW" and b25 == "REVIEW":
        return "Middle of the pack on both"
    if b23 == "WEAK" or b25 == "WEAK":
        return "Weak on at least one system — not recommended"
    return "Mixed — review drivers"


def _extract_held_symbols(
    scorecard: Optional[pd.DataFrame],
) -> List[str]:
    """Return the flat list of held Symbol + Scoring_Symbol values from an
    overlay scorecard, if one is supplied."""
    if scorecard is None or scorecard.empty:
        return []
    held: set = set()
    if "Symbol" in scorecard.columns:
        held.update(_ensure_string_symbol(scorecard["Symbol"]).str.upper())
    if "Scoring_Symbol" in scorecard.columns:
        held.update(_ensure_string_symbol(scorecard["Scoring_Symbol"]).str.upper())
    return sorted(h for h in held if h)


def _resolve_category(
    dual_table: pd.DataFrame,
    resolved_ticker: str,
    category_override: Optional[str],
) -> tuple:
    """Return (category, source). ``source`` ∈ {"override","universe","unknown"}."""
    if category_override:
        return str(category_override).strip(), "override"
    if dual_table.empty or "Category" not in dual_table.columns:
        return None, "unknown"
    sym_col = _ensure_string_symbol(dual_table["Symbol"]).str.upper()
    hit = dual_table.loc[sym_col == resolved_ticker]
    if hit.empty:
        return None, "unknown"
    cat = hit.iloc[0].get("Category")
    if cat is None or (isinstance(cat, float) and pd.isna(cat)):
        return None, "unknown"
    cat = str(cat).strip()
    return (cat if cat else None), ("universe" if cat else "unknown")


def _current_holding_profile(
    dual_table: pd.DataFrame,
    scorecard: Optional[pd.DataFrame],
    original_ticker: str,
    resolved_ticker: str,
    alias_applied: bool,
    model_name: Optional[str],
) -> pd.DataFrame:
    """Build a one-row DataFrame describing the current holding.

    Pulls scoring info from the dual table and, if available, augments with
    the model-level fields (Model_Name, Target_Weight_Pct, Overlay_Action)
    from the overlay scorecard.
    """
    base: Dict[str, Any] = {col: np.nan for col in PROFILE_COLUMNS}
    base["Symbol"] = original_ticker
    base["Scoring_Symbol"] = resolved_ticker
    base["Alias_Applied"] = bool(alias_applied)
    base["Scored_In_Universe"] = False

    if not dual_table.empty and "Symbol" in dual_table.columns:
        sym_col = _ensure_string_symbol(dual_table["Symbol"]).str.upper()
        hit = dual_table.loc[sym_col == resolved_ticker]
        if not hit.empty:
            row = hit.iloc[0]
            for col in (
                "Name", "Category", "Fund_Type",
                "Score_2023_Final", "Score_2025_Final", "Score_Gap",
                "Rank_2023", "Rank_2025", "Consensus_Rank",
                "Score_Band_2023", "Score_Band_2025", "Quadrant",
                "Action_Flag", "Primary_Driver",
                "Data_Coverage_2023", "Data_Coverage_2025",
            ):
                if col in hit.columns:
                    base[col] = row.get(col)
            base["Scored_In_Universe"] = True

    if scorecard is not None and not scorecard.empty:
        sc_sym = _ensure_string_symbol(scorecard["Symbol"]).str.upper() \
            if "Symbol" in scorecard.columns else pd.Series(dtype=str)
        sc_resolved = (
            _ensure_string_symbol(scorecard["Scoring_Symbol"]).str.upper()
            if "Scoring_Symbol" in scorecard.columns
            else pd.Series(dtype=str)
        )
        mask = (sc_sym == original_ticker) | (sc_resolved == resolved_ticker)
        if model_name:
            model_mask = scorecard["Model_Name"].astype(str) == str(model_name) \
                if "Model_Name" in scorecard.columns else pd.Series([False] * len(scorecard))
            narrowed = scorecard[mask & model_mask]
            if narrowed.empty:
                narrowed = scorecard[mask]
        else:
            narrowed = scorecard[mask]

        if not narrowed.empty:
            # Pick the row with the largest target weight when multiple models hold it.
            if "Target_Weight_Pct" in narrowed.columns:
                narrowed = narrowed.sort_values(
                    "Target_Weight_Pct", ascending=False, kind="stable",
                )
            row = narrowed.iloc[0]
            for col in ("Model_Name", "Target_Weight_Pct", "Overlay_Action"):
                if col in narrowed.columns:
                    base[col] = row.get(col)

    return pd.DataFrame([base], columns=PROFILE_COLUMNS)


def _candidate_pool(
    dual_table: pd.DataFrame,
    category: Optional[str],
    exclude_symbols: set,
    resolved_ticker: str,
) -> pd.DataFrame:
    """Filter the scored universe to same-category candidates, minus the
    current ticker and anything in ``exclude_symbols``.

    If ``category`` is None, returns an empty frame (caller decides how to
    surface the miss).
    """
    if dual_table.empty or not category:
        return dual_table.head(0)
    if "Category" not in dual_table.columns:
        return dual_table.head(0)

    d = dual_table.copy()
    d["Symbol"] = _ensure_string_symbol(d["Symbol"])
    sym_upper = d["Symbol"].str.upper()

    mask = d["Category"].astype(str).str.strip() == str(category).strip()
    mask &= sym_upper != resolved_ticker

    return d.loc[mask].copy()


def _rank_candidates(
    pool: pd.DataFrame,
    top_n: int,
    exclude_symbols: set,
    held_by_models_lookup: Mapping[str, List[str]],
    restrict_symbols: Optional[set] = None,
    annotation_universe: Optional[set] = None,
    name_overrides: Optional[Mapping[str, str]] = None,
) -> pd.DataFrame:
    """Rank the same-category pool by Consensus_Rank (best first) and flag
    anything already held.

    ``exclude_symbols`` removes candidates entirely. ``held_by_models_lookup``
    is used only to annotate ``Already_Held`` / ``Held_By_Models`` on the
    retained rows — the caller decides whether to exclude or flag.

    ``restrict_symbols`` (optional, upper-cased) keeps only rows whose Symbol
    appears in the supplied set — used to constrain the FundScore short list
    to the curated candidate-exposures universe.

    ``name_overrides`` (upper-case symbol -> name) replaces ``Name`` on the
    retained rows with the curated value when present, so staff-facing output
    matches the names the user typed in the candidate file.
    """
    if pool.empty:
        return pd.DataFrame(columns=CANDIDATE_COLUMNS)

    p = pool.copy()
    sym_upper = _ensure_string_symbol(p["Symbol"]).str.upper()
    if exclude_symbols:
        p = p.loc[~sym_upper.isin(exclude_symbols)].copy()
        sym_upper = _ensure_string_symbol(p["Symbol"]).str.upper()
    if restrict_symbols is not None:
        # An empty restrict_symbols set explicitly says "no candidates"; honor that.
        p = p.loc[sym_upper.isin(restrict_symbols)].copy()
        sym_upper = _ensure_string_symbol(p["Symbol"]).str.upper()

    sort_cols = []
    sort_asc: List[bool] = []
    if "Consensus_Rank" in p.columns:
        sort_cols.append("Consensus_Rank")
        sort_asc.append(True)
    if "Score_2025_Final" in p.columns:
        sort_cols.append("Score_2025_Final")
        sort_asc.append(False)
    if "Score_2023_Final" in p.columns:
        sort_cols.append("Score_2023_Final")
        sort_asc.append(False)
    sort_cols.append("Symbol")
    sort_asc.append(True)

    p = p.sort_values(
        sort_cols, ascending=sort_asc, kind="stable", na_position="last",
    )
    p = p.head(top_n).reset_index(drop=True)

    p.insert(0, "Rank", range(1, len(p) + 1))

    # Annotation columns — build without mutating the original held lookup.
    sym_upper_out = _ensure_string_symbol(p["Symbol"]).str.upper()
    already_held: List[bool] = []
    held_by: List[str] = []
    from_uploaded: List[bool] = []
    annotate_set = annotation_universe if annotation_universe is not None \
        else restrict_symbols
    for sym in sym_upper_out:
        models = held_by_models_lookup.get(sym, [])
        already_held.append(bool(models))
        held_by.append(", ".join(models))
        from_uploaded.append(
            bool(annotate_set is not None and sym in annotate_set)
        )
    p["Already_Held"] = already_held
    p["Held_By_Models"] = held_by
    p["From_Uploaded_Universe"] = from_uploaded

    # Preserve curated names from the uploaded candidate file when supplied.
    if name_overrides:
        new_names = []
        for sym, current in zip(sym_upper_out, p.get("Name", pd.Series([""] * len(p)))):
            override = name_overrides.get(sym)
            if override:
                new_names.append(override)
            else:
                new_names.append(current)
        p["Name"] = new_names

    p["Reason_Label"] = p.apply(_reason_label, axis=1)

    for col in CANDIDATE_COLUMNS:
        if col not in p.columns:
            p[col] = np.nan

    return p[CANDIDATE_COLUMNS]


def _held_by_models(scorecard: Optional[pd.DataFrame]) -> Dict[str, List[str]]:
    """Return {upper_symbol: [model_name, ...]} from an overlay scorecard."""
    out: Dict[str, List[str]] = {}
    if scorecard is None or scorecard.empty:
        return out
    if "Model_Name" not in scorecard.columns:
        return out
    sym_cols = []
    if "Symbol" in scorecard.columns:
        sym_cols.append("Symbol")
    if "Scoring_Symbol" in scorecard.columns:
        sym_cols.append("Scoring_Symbol")
    for col in sym_cols:
        for sym, model in zip(
            _ensure_string_symbol(scorecard[col]).str.upper(),
            scorecard["Model_Name"].astype(str),
        ):
            if not sym:
                continue
            out.setdefault(sym, [])
            if model and model not in out[sym]:
                out[sym].append(model)
    return out


def _render_brief(
    ticker: str,
    resolved_ticker: str,
    alias_applied: bool,
    category: Optional[str],
    category_source: str,
    profile: pd.DataFrame,
    candidates: pd.DataFrame,
    summary: Dict[str, Any],
) -> str:
    """Render a short Markdown research brief."""
    lines: List[str] = []
    lines.append(f"# Replacement Workbench — {ticker}")
    lines.append("")
    run_date = summary.get("run_date") or "—"
    lines.append(f"_Run: **{run_date}** · Generated: {summary.get('generated_at', '—')}_")
    lines.append("")

    lines.append("## Current holding")
    if alias_applied:
        lines.append(
            f"- **Ticker:** `{ticker}` "
            f"(resolved to scored symbol `{resolved_ticker}` via share-class alias)"
        )
    else:
        lines.append(f"- **Ticker:** `{ticker}`")
    if not profile.empty:
        row = profile.iloc[0]
        lines.append(f"- **Name:** {row.get('Name', '—') or '—'}")
        lines.append(
            f"- **Category:** {row.get('Category', '—') or '—'} "
            f"(source: {category_source})"
        )
        lines.append(f"- **Fund type:** {row.get('Fund_Type', '—') or '—'}")
        lines.append(
            f"- **2023 score:** {_format_float(row.get('Score_2023_Final'))} "
            f"(rank {_format_int(row.get('Rank_2023'))}, "
            f"band {row.get('Score_Band_2023') or '—'})"
        )
        lines.append(
            f"- **2025 score:** {_format_float(row.get('Score_2025_Final'))} "
            f"(rank {_format_int(row.get('Rank_2025'))}, "
            f"band {row.get('Score_Band_2025') or '—'})"
        )
        lines.append(
            f"- **Consensus rank:** {_format_int(row.get('Consensus_Rank'))} "
            f"· quadrant {row.get('Quadrant') or '—'}"
        )
        if pd.notna(row.get("Model_Name")):
            lines.append(
                f"- **Held by model:** {row.get('Model_Name')} "
                f"(target {_format_float(row.get('Target_Weight_Pct'))}%)"
            )
    lines.append("")

    lines.append("## Methodology")
    lines.append(
        "- Filter: **same Morningstar category** "
        f"(`{category or 'unknown'}`)."
    )
    if summary.get("restrict_to_candidate_exposures"):
        lines.append(
            "- **Candidate universe:** restricted to the uploaded curated "
            "candidate-exposures file "
            f"({summary.get('candidate_universe_size') or 0} symbol(s)). "
            "The full scored universe is **not** used for the staff-facing "
            "short list — only ideas the user vetted upstream."
        )
    else:
        lines.append(
            "- **Candidate universe:** full scored universe in the same "
            "category."
        )
    lines.append(
        "- Rank by **Consensus_Rank** (average of 2023 and 2025 ranks), "
        "best first. 2023 and 2025 scores/ranks are preserved side-by-side — "
        "disagreement is surfaced in the **Reason / Fit** column, never "
        "blended away."
    )
    if summary.get("exclude_already_held"):
        lines.append(
            "- **Already-held positions are excluded** by default — the "
            "current holding being replaced is the only allowed exception. "
            "This keeps passive positions like SPYM out of staff-facing "
            "active-replacement recommendations when those names already "
            "live in the model."
        )
    else:
        lines.append(
            "- Other currently-held tickers are flagged with "
            "**Already_Held** / **Held_By_Models** when an overlay "
            "scorecard is available."
        )
    lines.append("")

    lines.append(f"## Top {len(candidates)} same-category candidates")
    if candidates.empty:
        if category_source == "unknown":
            lines.append(
                "No candidate pool: the current holding is not in the scored "
                "universe and no category override was supplied."
            )
        else:
            lines.append(f"No same-category candidates found in `{category}`.")
    else:
        lines.append(
            "| # | Symbol | Name | Type | 2023 | 2025 | Cons. | Bands | Reason |"
        )
        lines.append(
            "|---|--------|------|------|------|------|-------|-------|--------|"
        )
        for _, row in candidates.iterrows():
            bands = (
                f"{row.get('Score_Band_2023') or '—'}/"
                f"{row.get('Score_Band_2025') or '—'}"
            )
            held_marker = " *(held)*" if bool(row.get("Already_Held")) else ""
            name = str(row.get("Name") or "—").replace("|", "/")
            reason = str(row.get("Reason_Label") or "—").replace("|", "/")
            lines.append(
                f"| {row.get('Rank', '—')} "
                f"| `{row.get('Symbol') or '—'}` "
                f"| {name}{held_marker} "
                f"| {row.get('Fund_Type') or '—'} "
                f"| {_format_float(row.get('Score_2023_Final'))} "
                f"| {_format_float(row.get('Score_2025_Final'))} "
                f"| {_format_int(row.get('Consensus_Rank'))} "
                f"| {bands} "
                f"| {reason} |"
            )
    lines.append("")

    if summary.get("benchmark_fit_enabled"):
        lines.append("## Benchmark fit")
        lines.append(
            f"- **Current sleeve fit:** {summary.get('baseline_fit_label', '—')} "
            f"(total active drift "
            f"{_format_float(summary.get('baseline_total_abs_drift'), 3)}, "
            f"max bucket "
            f"`{summary.get('baseline_max_drift_bucket') or '—'}` "
            f"@ {_format_float(summary.get('baseline_max_abs_drift'), 3)})"
        )
        bw = summary.get("benchmark_weights") or {}
        if bw:
            wstr = ", ".join(f"{k} {v:.0%}" for k, v in bw.items())
            lines.append(f"- **Benchmark weights:** {wstr}")
        bf = summary.get("best_fundscore_candidate") or "—"
        bfit = summary.get("best_benchmark_fit_candidate") or "—"
        bal = summary.get("balanced_candidate") or "—"
        lines.append(f"- **Best by FundScore:** `{bf}`")
        lines.append(f"- **Best by benchmark fit:** `{bfit}`")
        lines.append(f"- **Balanced (FundScore + fit):** `{bal}`")
        lines.append(
            "- Drift math: active = current model − benchmark, summed by "
            "stylebox + sector buckets. Lower total/max drift is closer to "
            "the static 100/0 equity benchmark."
        )
        lines.append("")

    lines.append("## Notes")
    lines.append(
        "- This is a short list for replacement research, not an "
        "investment recommendation. Confirm current share-class availability, "
        "minimums, and operational fit before recommending to the committee."
    )
    lines.append(
        "- This workbench is separate from the monthly committee packet. "
        "Use the overlay + Excel audit workbook for the full monthly review."
    )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_replacement_workbench(
    dual_table: pd.DataFrame,
    ticker: str,
    *,
    scorecard: Optional[pd.DataFrame] = None,
    model_name: Optional[str] = None,
    category_override: Optional[str] = None,
    top_n: int = DEFAULT_TOP_N,
    exclude_held: bool = False,
    alias_map: Optional[Mapping[str, str]] = None,
    run_date: Optional[str] = None,
    model_holdings: Optional[pd.DataFrame] = None,
    model_exposures: Optional[pd.DataFrame] = None,
    benchmark_exposures: Optional[pd.DataFrame] = None,
    benchmark_weights: Optional[Mapping[str, float]] = None,
    candidate_exposures: Optional[pd.DataFrame] = None,
    candidate_universe_mode: str = "auto",
    restrict_to_candidate_exposures: Optional[bool] = None,
    exclude_already_held: Optional[bool] = None,
) -> ReplacementResult:
    """Build replacement short list artifacts for a single ticker.

    Parameters
    ----------
    dual_table:
        Canonical dual-score table (one row per Symbol).
    ticker:
        The committee-facing / model-library symbol to research (e.g. ``PRBLX``).
    scorecard:
        Optional overlay ``model_holdings_scorecard`` DataFrame. Used to
        annotate ``Already_Held`` / ``Held_By_Models`` on candidates and to
        augment the current-holding profile with Model_Name / Target_Weight_Pct.
    model_name:
        Optional model filter when the same ticker appears in multiple
        models — ties the profile to a specific model row.
    category_override:
        Category string to use when the resolved ticker is missing from the
        scored universe, or when the user wants to force a different peer
        group. When set, takes precedence over the universe-derived value.
    top_n:
        Max candidate rows to retain. Default ``DEFAULT_TOP_N``.
    exclude_held:
        When True, exclude candidates currently held by any model in the
        overlay scorecard. When False (default) they are still included but
        the ``Already_Held`` / ``Held_By_Models`` columns flag them.
    alias_map:
        Optional Original_Symbol -> Scoring_Symbol map. Defaults to
        ``load_default_aliases()`` so known share-class pairs (PRBLX -> PRILX
        etc.) reconcile without hand-editing the input.
    run_date:
        Optional ISO date string from the caller's run archive, recorded in
        the summary and brief for provenance.
    candidate_universe_mode:
        ``"auto"`` (default) restricts the FundScore short list and the
        benchmark-fit ranking to the curated symbols in
        ``candidate_exposures`` whenever that file is supplied. ``"uploaded"``
        forces that restriction (warns if no candidate file). ``"scored"``
        keeps the legacy behavior — rank against the full scored universe.
    restrict_to_candidate_exposures:
        Explicit override for ``candidate_universe_mode``. ``True`` always
        restricts to the uploaded universe (no-op when no file supplied);
        ``False`` always uses the full scored universe.
    exclude_already_held:
        When ``True``, drop symbols held by *any* model in the overlay
        scorecard from the staff-facing candidate list (still allowed:
        the current-holding ticker being replaced). Defaults to ``True``
        when ``candidate_exposures`` is supplied (curated active-replacement
        flow), otherwise ``False`` for backwards compatibility. Overrides
        ``exclude_held`` when explicitly set.
    """
    if alias_map is None:
        alias_map = load_default_aliases()

    if candidate_universe_mode not in CANDIDATE_UNIVERSE_MODES:
        raise ValueError(
            f"candidate_universe_mode must be one of {CANDIDATE_UNIVERSE_MODES}; "
            f"got {candidate_universe_mode!r}."
        )

    original = _norm(ticker)
    if not original:
        raise ValueError("Ticker must be a non-empty string.")
    if top_n <= 0:
        raise ValueError("top_n must be a positive integer.")

    universe = set()
    if not dual_table.empty and "Symbol" in dual_table.columns:
        universe = {
            _norm(s) for s in dual_table["Symbol"].dropna().astype(str).tolist()
        }

    resolved = resolve_symbol(original, alias_map, universe)
    alias_applied = bool(resolved and resolved != original)

    category, cat_source = _resolve_category(dual_table, resolved, category_override)

    held_lookup = _held_by_models(scorecard)
    held_symbols = _extract_held_symbols(scorecard)

    # Build the curated candidate universe (symbols + display names) when
    # the caller supplied a candidate_exposures file.
    candidate_universe_symbols: Optional[set] = None
    candidate_name_overrides: Dict[str, str] = {}
    has_candidate_file = (
        candidate_exposures is not None and not candidate_exposures.empty
        and "Symbol" in candidate_exposures.columns
    )
    if has_candidate_file:
        sym_col = (
            candidate_exposures["Symbol"].astype(str).str.strip().str.upper()
        )
        candidate_universe_symbols = {s for s in sym_col.tolist() if s}
        if "Name" in candidate_exposures.columns:
            for s, n in zip(sym_col.tolist(),
                             candidate_exposures["Name"].astype(str).tolist()):
                if s and n and n.strip():
                    candidate_name_overrides[s] = n.strip()

    # Resolve the universe-mode flags into a single boolean for the pool.
    if restrict_to_candidate_exposures is None:
        if candidate_universe_mode == "uploaded":
            restrict_resolved = True
        elif candidate_universe_mode == "scored":
            restrict_resolved = False
        else:  # "auto"
            restrict_resolved = bool(has_candidate_file)
    else:
        restrict_resolved = bool(restrict_to_candidate_exposures)

    if restrict_resolved and not has_candidate_file:
        # Caller asked to restrict but supplied no curated universe — the
        # only honest response is "no candidates from the curated list".
        # Surface that via an empty candidate_universe_symbols set so
        # _rank_candidates filters everything out and the summary records
        # the miss.
        candidate_universe_symbols = set()

    # Distinct from ``candidate_universe_symbols`` (which we keep populated
    # for diagnostics and for the From_Uploaded_Universe annotation), this
    # is the set actually used to filter the FundScore short list. Only
    # restrict the pool when the caller asked for restricted mode.
    pool_restrict_symbols: Optional[set] = (
        candidate_universe_symbols if restrict_resolved else None
    )

    # Resolve exclude_already_held, defaulting True when a candidate file
    # is present so SPYM (etc.) can't slip into the curated active list.
    if exclude_already_held is None:
        exclude_already_held_resolved = bool(has_candidate_file)
    else:
        exclude_already_held_resolved = bool(exclude_already_held)
    # Legacy ``exclude_held`` still wins when explicitly truthy.
    if exclude_held and not exclude_already_held_resolved:
        exclude_already_held_resolved = True

    exclude: set = {original, resolved}
    if exclude_already_held_resolved:
        held_excluding_target = {
            s for s in held_symbols if s not in {original, resolved}
        }
        exclude.update(held_excluding_target)

    pool = _candidate_pool(dual_table, category, exclude, resolved)

    candidates = _rank_candidates(
        pool, top_n=top_n, exclude_symbols=exclude,
        held_by_models_lookup=held_lookup,
        restrict_symbols=pool_restrict_symbols,
        annotation_universe=candidate_universe_symbols,
        name_overrides=candidate_name_overrides,
    )

    profile = _current_holding_profile(
        dual_table,
        scorecard,
        original_ticker=original,
        resolved_ticker=resolved,
        alias_applied=alias_applied,
        model_name=model_name,
    )

    summary: Dict[str, Any] = {
        "ticker": original,
        "resolved_ticker": resolved,
        "alias_applied": bool(alias_applied),
        "model_name": model_name,
        "category": category,
        "category_source": cat_source,
        "category_override_used": bool(category_override),
        "top_n_requested": int(top_n),
        "candidate_count": int(len(candidates)),
        "already_held_candidate_count": int(candidates["Already_Held"].sum())
            if "Already_Held" in candidates.columns and not candidates.empty else 0,
        "current_in_universe": bool(profile.iloc[0]["Scored_In_Universe"])
            if not profile.empty else False,
        "current_score_2023": (
            float(profile.iloc[0]["Score_2023_Final"])
            if not profile.empty
            and pd.notna(profile.iloc[0]["Score_2023_Final"])
            else None
        ),
        "current_score_2025": (
            float(profile.iloc[0]["Score_2025_Final"])
            if not profile.empty
            and pd.notna(profile.iloc[0]["Score_2025_Final"])
            else None
        ),
        "exclude_held_requested": bool(exclude_held),
        "exclude_already_held": bool(exclude_already_held_resolved),
        "candidate_universe_mode": candidate_universe_mode,
        "restrict_to_candidate_exposures": bool(restrict_resolved),
        "candidate_universe_size": (
            int(len(candidate_universe_symbols))
            if candidate_universe_symbols is not None else None
        ),
        "candidate_universe_source": (
            "uploaded" if has_candidate_file and restrict_resolved
            else ("scored" if not restrict_resolved else "uploaded_empty")
        ),
        "universe_row_count": int(len(dual_table)),
        "category_pool_size": int(len(pool)),
        "held_symbol_count": int(len(held_symbols)),
        "run_date": run_date,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }

    # Benchmark-fit layer (optional). Adds drift columns to candidates and
    # produces the three exposure artifacts when all four exposure inputs
    # are present.
    fit_candidates_table = pd.DataFrame()
    current_vs_benchmark = pd.DataFrame()
    replacement_delta = pd.DataFrame()
    if (
        model_holdings is not None
        and model_exposures is not None
        and benchmark_exposures is not None
        and benchmark_weights is not None
    ):
        from benchmark_fit import (
            DEFAULT_BENCHMARK_WEIGHTS,
            build_benchmark_fit_artifacts,
        )

        bench_w = dict(benchmark_weights) if benchmark_weights \
            else dict(DEFAULT_BENCHMARK_WEIGHTS)

        # If the caller supplied no candidate exposure file, fall back to
        # whatever's present in candidate / model exposures so we still
        # have a chance of computing fit for ranked candidates.
        cand_exp = candidate_exposures
        if cand_exp is None or cand_exp.empty:
            cand_exp = model_exposures

        # Build the candidate universe for fit ranking.
        #   * Restricted mode (curated active flow): rank ONLY the uploaded
        #     candidate-file symbols, so SPYM / model-exposure-only tickers
        #     can't slip into the staff-facing benchmark-fit ranking.
        #   * Open mode (legacy): union the FundScore short list with the
        #     candidate-file so prior callers keep their behavior.
        cand_syms_set: set = set()
        if restrict_resolved and candidate_universe_symbols is not None:
            cand_syms_set.update(candidate_universe_symbols)
        else:
            if not candidates.empty:
                cand_syms_set.update(
                    candidates["Symbol"].astype(str).str.strip()
                    .str.upper().tolist()
                )
            if cand_exp is not None and not cand_exp.empty \
                    and "Symbol" in cand_exp.columns:
                cand_syms_set.update(
                    cand_exp["Symbol"].astype(str).str.strip()
                    .str.upper().tolist()
                )

        # Drop already-held tickers (other than the current holding being
        # replaced) from the fit ranking when exclude_already_held is on.
        if exclude_already_held_resolved:
            cand_syms_set -= {
                s for s in held_symbols if s not in {original, resolved}
            }
        cand_syms_set.discard(original)
        cand_syms_set.discard(resolved)
        cand_syms = sorted(s for s in cand_syms_set if s)

        # Holdings + exposure files use the committee-facing ticker
        # (e.g. PRBLX), while ``resolved`` is the scored alias target
        # (e.g. PRILX). Use the original for the holdings lookup so the
        # simulation finds the row to replace; fall back to the resolved
        # form if the original isn't present.
        holdings_syms_upper = (
            model_holdings["Symbol"].astype(str).str.strip().str.upper().tolist()
            if "Symbol" in model_holdings.columns else []
        )
        target_for_sim = original if original in holdings_syms_upper else resolved

        fit = build_benchmark_fit_artifacts(
            model_holdings=model_holdings,
            model_exposures=model_exposures,
            benchmark_exposures=benchmark_exposures,
            benchmark_weights=bench_w,
            candidate_exposures=cand_exp,
            target_symbol=target_for_sim,
            candidate_symbols=cand_syms,
        )

        current_vs_benchmark = fit["current_vs_benchmark"]
        fit_candidates_table = fit["replacement_table"]
        replacement_delta = fit["replacement_delta"]

        # Annotate the benchmark-fit ranking so staff-facing artifacts make
        # the curated source obvious. Add Already_Held + From_Uploaded_Universe
        # + curated Name (preferred over the scored-universe name).
        if not fit_candidates_table.empty:
            sym_u = (
                fit_candidates_table["Candidate_Symbol"]
                .astype(str).str.strip().str.upper()
            )
            held_set_minus_current = {
                s for s in held_symbols if s not in {original, resolved}
            }
            fit_candidates_table["Already_Held"] = sym_u.isin(
                held_set_minus_current
            ).tolist()
            fit_candidates_table["From_Uploaded_Universe"] = (
                sym_u.isin(candidate_universe_symbols or set()).tolist()
            )
            # Display name resolution: prefer curated Name from
            # candidate_exposures, else fall back to the scored universe.
            scored_name_lookup: Dict[str, str] = {}
            if not dual_table.empty and "Symbol" in dual_table.columns \
                    and "Name" in dual_table.columns:
                for s, n in zip(
                    dual_table["Symbol"].astype(str).str.strip().str.upper(),
                    dual_table["Name"].astype(str),
                ):
                    if s and n:
                        scored_name_lookup.setdefault(s, n)
            display_names: List[str] = []
            for s in sym_u.tolist():
                nm = candidate_name_overrides.get(s) \
                    or scored_name_lookup.get(s, "")
                display_names.append(nm)
            fit_candidates_table.insert(2, "Name", display_names)

        if not fit_candidates_table.empty and not candidates.empty:
            cand_lower = candidates.copy()
            cand_lower["Symbol_U"] = (
                cand_lower["Symbol"].astype(str).str.strip().str.upper()
            )
            fit_lower = fit_candidates_table.copy()
            fit_lower["Symbol_U"] = (
                fit_lower["Candidate_Symbol"].astype(str).str.strip().str.upper()
            )
            keep = [
                "Symbol_U",
                "Total_Abs_Drift_After",
                "Total_Abs_Drift_Change",
                "Max_Abs_Drift_After",
                "Stylebox_Drift_After",
                "Sector_Drift_After",
                "Fit_Label",
                "Fit_Rank",
            ]
            cand_lower = cand_lower.merge(
                fit_lower[keep], on="Symbol_U", how="left",
            )
            cand_lower = cand_lower.drop(columns=["Symbol_U"])
            candidates = cand_lower

        # Summary entries: best by FundScore vs best by benchmark-fit vs
        # balanced compromise. Prefer non-already-held picks at the top so
        # the headline recommendations don't double up an existing model
        # position.
        best_fundscore = None
        if not candidates.empty:
            cand_for_pick = candidates
            if "Already_Held" in cand_for_pick.columns:
                non_held = cand_for_pick[~cand_for_pick["Already_Held"].astype(bool)]
                if not non_held.empty:
                    cand_for_pick = non_held
            best_fundscore = str(cand_for_pick.iloc[0]["Symbol"])

        best_fit = None
        if not fit_candidates_table.empty:
            fit_for_pick = fit_candidates_table
            if "Already_Held" in fit_for_pick.columns:
                non_held = fit_for_pick[~fit_for_pick["Already_Held"].astype(bool)]
                if not non_held.empty:
                    fit_for_pick = non_held
            best_fit = str(fit_for_pick.iloc[0]["Candidate_Symbol"])

        balanced = None
        if not candidates.empty and "Fit_Rank" in candidates.columns:
            cand_with_fit = candidates.dropna(subset=["Fit_Rank"]).copy()
            if "Already_Held" in cand_with_fit.columns:
                non_held = cand_with_fit[~cand_with_fit["Already_Held"].astype(bool)]
                if not non_held.empty:
                    cand_with_fit = non_held
            if not cand_with_fit.empty and "Consensus_Rank" in cand_with_fit.columns:
                cand_with_fit["_combined"] = (
                    cand_with_fit["Consensus_Rank"].rank(method="min")
                    + cand_with_fit["Fit_Rank"].rank(method="min")
                )
                cand_with_fit = cand_with_fit.sort_values(
                    ["_combined", "Symbol"], kind="stable",
                )
                balanced = str(cand_with_fit.iloc[0]["Symbol"])

        summary["benchmark_fit_enabled"] = True
        summary["benchmark_weights"] = {
            k: float(v) for k, v in bench_w.items()
        }
        summary["baseline_fit_label"] = fit["baseline_fit_label"]
        summary["baseline_total_abs_drift"] = float(
            fit["baseline_metrics"]["total_abs_drift"]
        )
        summary["baseline_max_abs_drift"] = float(
            fit["baseline_metrics"]["max_abs_drift"]
        )
        summary["baseline_max_drift_bucket"] = (
            fit["baseline_metrics"]["max_drift_bucket"]
        )
        summary["best_fundscore_candidate"] = best_fundscore
        summary["best_benchmark_fit_candidate"] = best_fit
        summary["balanced_candidate"] = balanced
        summary["benchmark_fit_candidate_count"] = int(len(fit_candidates_table))
        summary["missing_holdings_exposures"] = list(fit["missing_holdings"])
        summary["missing_benchmark_exposures"] = list(fit["missing_benchmark"])
    else:
        summary["benchmark_fit_enabled"] = False

    brief = _render_brief(
        ticker=original,
        resolved_ticker=resolved,
        alias_applied=alias_applied,
        category=category,
        category_source=cat_source,
        profile=profile,
        candidates=candidates,
        summary=summary,
    )

    return ReplacementResult(
        ticker=original,
        resolved_ticker=resolved,
        alias_applied=alias_applied,
        category=category,
        category_source=cat_source,
        candidates=candidates,
        current_profile=profile,
        summary=summary,
        brief_markdown=brief,
        held_symbols=held_symbols,
        benchmark_fit_candidates=fit_candidates_table,
        current_vs_benchmark=current_vs_benchmark,
        replacement_delta=replacement_delta,
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def workbench_dir(runs_dir: str, run_date: str, ticker: str) -> str:
    """Canonical absolute path for a ticker's workbench artifacts."""
    return os.path.join(
        runs_dir, run_date, WORKBENCH_SUBDIR, _norm(ticker) or "UNKNOWN",
    )


def write_replacement(result: ReplacementResult, out_dir: str) -> Dict[str, str]:
    """Persist the canonical artifacts. Returns {name: path}.

    The benchmark-fit artifacts are written only when the corresponding
    DataFrames are non-empty — i.e., when the caller supplied exposure data.
    """
    os.makedirs(out_dir, exist_ok=True)
    paths: Dict[str, str] = {}

    candidates_path = os.path.join(out_dir, CANDIDATES_NAME)
    result.candidates.to_csv(candidates_path, index=False)
    paths["candidates"] = candidates_path

    profile_path = os.path.join(out_dir, CURRENT_PROFILE_NAME)
    result.current_profile.to_csv(profile_path, index=False)
    paths["current_profile"] = profile_path

    summary_path = os.path.join(out_dir, SUMMARY_NAME)
    with open(summary_path, "w") as f:
        json.dump(result.summary, f, indent=2, sort_keys=True, default=str)
    paths["summary"] = summary_path

    brief_path = os.path.join(out_dir, BRIEF_NAME)
    with open(brief_path, "w") as f:
        f.write(result.brief_markdown)
    paths["brief"] = brief_path

    if not result.benchmark_fit_candidates.empty:
        bf_path = os.path.join(out_dir, BENCHMARK_FIT_CANDIDATES_NAME)
        result.benchmark_fit_candidates.to_csv(bf_path, index=False)
        paths["benchmark_fit_candidates"] = bf_path
    if not result.current_vs_benchmark.empty:
        cb_path = os.path.join(out_dir, CURRENT_VS_BENCHMARK_NAME)
        result.current_vs_benchmark.to_csv(cb_path, index=False)
        paths["current_vs_benchmark"] = cb_path
    if not result.replacement_delta.empty:
        rd_path = os.path.join(out_dir, REPLACEMENT_DELTA_NAME)
        result.replacement_delta.to_csv(rd_path, index=False)
        paths["replacement_delta"] = rd_path

    return paths


def load_replacement(out_dir: str) -> Optional[Dict[str, Any]]:
    """Load previously-persisted workbench artifacts. None if absent."""
    if not os.path.isdir(out_dir):
        return None
    candidates_path = os.path.join(out_dir, CANDIDATES_NAME)
    if not os.path.isfile(candidates_path):
        return None

    def _safe_read_csv(name: str) -> pd.DataFrame:
        path = os.path.join(out_dir, name)
        if not os.path.isfile(path):
            return pd.DataFrame()
        try:
            return pd.read_csv(path)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()

    summary: Dict[str, Any] = {}
    summary_path = os.path.join(out_dir, SUMMARY_NAME)
    if os.path.isfile(summary_path):
        try:
            with open(summary_path) as f:
                summary = json.load(f)
        except json.JSONDecodeError:
            summary = {}

    brief = ""
    brief_path = os.path.join(out_dir, BRIEF_NAME)
    if os.path.isfile(brief_path):
        with open(brief_path) as f:
            brief = f.read()

    return {
        "path": out_dir,
        "candidates": _safe_read_csv(CANDIDATES_NAME),
        "current_profile": _safe_read_csv(CURRENT_PROFILE_NAME),
        "summary": summary,
        "brief_markdown": brief,
        "benchmark_fit_candidates": _safe_read_csv(BENCHMARK_FIT_CANDIDATES_NAME),
        "current_vs_benchmark": _safe_read_csv(CURRENT_VS_BENCHMARK_NAME),
        "replacement_delta": _safe_read_csv(REPLACEMENT_DELTA_NAME),
    }


# ---------------------------------------------------------------------------
# High-level convenience — build directly from an archived run
# ---------------------------------------------------------------------------

def run_replacement_for_run(
    run_date: str,
    ticker: str,
    *,
    runs_dir: Optional[str] = None,
    model_name: Optional[str] = None,
    category_override: Optional[str] = None,
    top_n: int = DEFAULT_TOP_N,
    exclude_held: bool = False,
    persist: bool = True,
    alias_csv_path: Optional[str] = None,
    model_holdings: Optional[pd.DataFrame] = None,
    model_exposures: Optional[pd.DataFrame] = None,
    benchmark_exposures: Optional[pd.DataFrame] = None,
    benchmark_weights: Optional[Mapping[str, float]] = None,
    candidate_exposures: Optional[pd.DataFrame] = None,
    candidate_universe_mode: str = "auto",
    restrict_to_candidate_exposures: Optional[bool] = None,
    exclude_already_held: Optional[bool] = None,
) -> Dict[str, Any]:
    """Build + (optionally) persist a workbench for ``ticker`` against the
    archived run at ``run_date``.

    Returns a dict with the ReplacementResult + written artifact paths.
    """
    # Local import keeps this module importable without the full run-archive
    # chain when all a caller has is an in-memory dual-score table.
    from run_archive import DEFAULT_RUNS_DIR, load_run
    from model_holdings_overlay import load_overlay
    from run_archive import run_overlay_dir

    rd = runs_dir or DEFAULT_RUNS_DIR
    run = load_run(run_date, runs_dir=rd)

    scorecard: Optional[pd.DataFrame] = None
    overlay = load_overlay(run_overlay_dir(rd, run_date))
    if overlay is not None:
        scorecard = overlay.get("scorecard")

    alias_map = load_default_aliases(extra_path=alias_csv_path)

    result = build_replacement_workbench(
        dual_table=run["table"],
        ticker=ticker,
        scorecard=scorecard,
        model_name=model_name,
        category_override=category_override,
        top_n=top_n,
        exclude_held=exclude_held,
        alias_map=alias_map,
        run_date=run_date,
        model_holdings=model_holdings,
        model_exposures=model_exposures,
        benchmark_exposures=benchmark_exposures,
        benchmark_weights=benchmark_weights,
        candidate_exposures=candidate_exposures,
        candidate_universe_mode=candidate_universe_mode,
        restrict_to_candidate_exposures=restrict_to_candidate_exposures,
        exclude_already_held=exclude_already_held,
    )

    paths: Dict[str, str] = {}
    out_dir = workbench_dir(rd, run_date, ticker)
    if persist:
        paths = write_replacement(result, out_dir)

    return {
        "run_date": run_date,
        "path": out_dir,
        "paths": paths,
        "result": result,
        "candidates": result.candidates,
        "current_profile": result.current_profile,
        "summary": result.summary,
        "brief_markdown": result.brief_markdown,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_build(args: argparse.Namespace) -> int:
    # Import here to avoid tying module import to the full archive chain.
    from run_archive import DEFAULT_RUNS_DIR, load_latest_run

    runs_dir = args.runs_dir or DEFAULT_RUNS_DIR
    run_date = args.run_date
    if run_date is None:
        latest = load_latest_run(runs_dir=runs_dir)
        run_date = latest["run_date"]

    bundle = run_replacement_for_run(
        run_date=run_date,
        ticker=args.ticker,
        runs_dir=runs_dir,
        model_name=args.model_name,
        category_override=args.category,
        top_n=args.top_n,
        exclude_held=args.exclude_held,
        persist=not args.dry_run,
        alias_csv_path=args.alias_csv,
        candidate_universe_mode=args.candidate_universe_mode,
        exclude_already_held=(
            False if args.include_already_held else None
        ),
    )
    result: ReplacementResult = bundle["result"]
    summary = bundle["summary"]

    print(
        f"Workbench for {result.ticker} "
        f"(resolved={result.resolved_ticker}, "
        f"category={result.category or 'unknown'} "
        f"[{result.category_source}]): "
        f"{len(result.candidates)} candidate(s)."
    )
    if summary.get("already_held_candidate_count"):
        print(
            f"  · {summary['already_held_candidate_count']} candidate(s) "
            "flagged as already-held."
        )
    if not args.dry_run and bundle["paths"]:
        for key, path in bundle["paths"].items():
            print(f"  wrote {key}: {path}")
    return 0


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Build a single-ticker replacement short list from an "
                    "archived scoring run.",
    )
    parser.add_argument(
        "--runs-dir", default=None,
        help="Runs directory (default: streamlit/runs).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Build a replacement short list.")
    p_build.add_argument(
        "--run-date", default=None,
        help="Archived run date (YYYY-MM-DD). Defaults to latest run.",
    )
    p_build.add_argument(
        "--ticker", required=True,
        help="Committee-facing ticker to replace (e.g. PRBLX).",
    )
    p_build.add_argument(
        "--model-name", default=None,
        help="Optional model filter when the ticker appears in multiple models.",
    )
    p_build.add_argument(
        "--category", default=None,
        help="Override category when the ticker isn't in the scored universe.",
    )
    p_build.add_argument(
        "--top-n", type=int, default=DEFAULT_TOP_N,
        help="Number of candidate rows to retain (default: 10).",
    )
    p_build.add_argument(
        "--exclude-held", action="store_true",
        help="Drop candidates already held by any model, rather than flagging.",
    )
    p_build.add_argument(
        "--candidate-universe-mode",
        choices=list(CANDIDATE_UNIVERSE_MODES),
        default="auto",
        help="auto (default; restrict when --candidate-exposures is supplied), "
             "uploaded (always restrict to candidate-exposures), "
             "scored (always use the full scored universe).",
    )
    p_build.add_argument(
        "--include-already-held", action="store_true",
        help="Override the default exclude-already-held behavior so passive "
             "or other model-held tickers can show up in the candidate list. "
             "By default already-held names are excluded when a candidate "
             "exposure file is supplied.",
    )
    p_build.add_argument(
        "--alias-csv", default=None,
        help="Optional alias CSV layered on top of the defaults.",
    )
    p_build.add_argument(
        "--dry-run", action="store_true",
        help="Compute but do not persist artifacts.",
    )
    p_build.set_defaults(func=_cmd_build)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    _cli()
