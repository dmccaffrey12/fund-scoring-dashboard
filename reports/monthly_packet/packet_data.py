"""
Monthly packet data loader.

Resolves a run-archive directory (produced by `streamlit/run_archive.py`)
and reads the inputs the Quarto packet consumes:

    <run_dir>/data/dual_score_table.csv            (required)
    <run_dir>/metadata/run_metadata.json           (required)
    <run_dir>/validation/validation_report.json    (optional)
    <run_dir>/validation/intake_report.json        (optional)
    <run_dir>/comparison/prior_<YYYY-MM-DD>/       (optional)
        summary.json
        score_movers.csv
        band_changes.csv
        quadrant_changes.csv
        action_flag_changes.csv
        new_funds.csv
        removed_funds.csv

Resolution order (first match wins):
    1. Explicit `run_path` argument / `FUND_PACKET_RUN_PATH` env var.
    2. `run_date` argument / `FUND_PACKET_RUN_DATE` env var, looked up under
       `runs_dir`.
    3. `runs_dir / latest.json` manifest.
    4. Lexicographic maximum of dated subdirectories under `runs_dir`.
    5. `FUND_PACKET_RUNS_DIR` env var overrides the default runs dir.

Every loader tolerates missing optional files so the packet still renders
with clear placeholders.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd


_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir, os.pardir))
DEFAULT_RUNS_DIR = os.path.join(_REPO_ROOT, "streamlit", "runs")
LATEST_MANIFEST = "latest.json"

DATA_FILE = os.path.join("data", "dual_score_table.csv")
METADATA_FILE = os.path.join("metadata", "run_metadata.json")
VALIDATION_FILE = os.path.join("validation", "validation_report.json")
INTAKE_FILE = os.path.join("validation", "intake_report.json")
COMPARISON_DIR = "comparison"

MODEL_OVERLAY_DIR = "model_holdings"
OVERLAY_SUMMARY_FILE = "model_summary.csv"
OVERLAY_SCORECARD_FILE = "model_holdings_scorecard.csv"
OVERLAY_CURRENT_REVIEW_FILE = "current_holdings_review.csv"
OVERLAY_REPLACEMENT_FILE = "replacement_candidates.csv"
OVERLAY_RESEARCH_FILE = "research_candidates.csv"
OVERLAY_METADATA_FILE = "overlay_metadata.json"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class PacketInputs:
    """Loaded packet inputs. Optional pieces are `None` when not present."""
    run_path: str
    run_date: str
    dual_score_table: pd.DataFrame
    metadata: Dict[str, Any]
    validation: Optional[Dict[str, Any]] = None
    intake: Optional[Dict[str, Any]] = None
    comparison: Optional["ComparisonBundle"] = None
    model_overlay: Optional["ModelOverlayBundle"] = None
    warnings: List[str] = field(default_factory=list)

    @property
    def has_comparison(self) -> bool:
        return self.comparison is not None

    @property
    def has_model_overlay(self) -> bool:
        return self.model_overlay is not None


@dataclass
class ModelOverlayBundle:
    """Loaded model-holdings overlay artifacts for a run."""
    path: str
    summary: pd.DataFrame
    scorecard: pd.DataFrame
    current_review: pd.DataFrame
    replacement_candidates: pd.DataFrame
    research_candidates: pd.DataFrame
    metadata: Dict[str, Any]


@dataclass
class ComparisonBundle:
    """Loaded month-over-month comparison for a run."""
    path: str
    latest_date: str
    prior_date: str
    summary: Dict[str, Any]
    score_movers: pd.DataFrame
    band_changes: pd.DataFrame
    quadrant_changes: pd.DataFrame
    action_flag_changes: pd.DataFrame
    new_funds: pd.DataFrame
    removed_funds: pd.DataFrame


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def _read_json_if_present(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _read_csv_if_present(path: str) -> Optional[pd.DataFrame]:
    if not os.path.isfile(path):
        return None
    try:
        return pd.read_csv(path)
    except Exception:
        return None


def _is_run_dir(path: str) -> bool:
    return (
        os.path.isdir(path)
        and os.path.isfile(os.path.join(path, DATA_FILE))
        and os.path.isfile(os.path.join(path, METADATA_FILE))
    )


def _resolve_from_manifest(runs_dir: str) -> Optional[str]:
    manifest_path = os.path.join(runs_dir, LATEST_MANIFEST)
    payload = _read_json_if_present(manifest_path)
    if not payload:
        return None
    candidate = payload.get("run_date") or payload.get("relative_path")
    if not candidate:
        return None
    full = os.path.join(runs_dir, candidate)
    return full if _is_run_dir(full) else None


def _resolve_latest_by_name(runs_dir: str) -> Optional[str]:
    if not os.path.isdir(runs_dir):
        return None
    dated = [
        name for name in os.listdir(runs_dir)
        if _DATE_RE.match(name) and _is_run_dir(os.path.join(runs_dir, name))
    ]
    if not dated:
        return None
    return os.path.join(runs_dir, sorted(dated)[-1])


def resolve_run_path(
    run_path: Optional[str] = None,
    run_date: Optional[str] = None,
    runs_dir: Optional[str] = None,
) -> Optional[str]:
    """Pick a run directory using the arg / env-var / manifest waterfall."""
    run_path = run_path or os.environ.get("FUND_PACKET_RUN_PATH")
    if run_path:
        run_path = os.path.abspath(os.path.expanduser(run_path))
        return run_path if _is_run_dir(run_path) else None

    runs_dir = (
        runs_dir
        or os.environ.get("FUND_PACKET_RUNS_DIR")
        or DEFAULT_RUNS_DIR
    )
    runs_dir = os.path.abspath(os.path.expanduser(runs_dir))

    run_date = run_date or os.environ.get("FUND_PACKET_RUN_DATE")
    if run_date:
        candidate = os.path.join(runs_dir, run_date)
        if _is_run_dir(candidate):
            return candidate
        return None

    manifest_hit = _resolve_from_manifest(runs_dir)
    if manifest_hit:
        return manifest_hit
    return _resolve_latest_by_name(runs_dir)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_comparison(run_path: str) -> Optional[ComparisonBundle]:
    comp_root = os.path.join(run_path, COMPARISON_DIR)
    if not os.path.isdir(comp_root):
        return None

    prior_dirs = sorted(
        d for d in os.listdir(comp_root)
        if d.startswith("prior_")
        and os.path.isdir(os.path.join(comp_root, d))
        and _DATE_RE.match(d[len("prior_"):])
    )
    if not prior_dirs:
        return None

    chosen = os.path.join(comp_root, prior_dirs[-1])
    summary = _read_json_if_present(os.path.join(chosen, "summary.json"))
    if summary is None:
        return None

    def _csv(name: str) -> pd.DataFrame:
        df = _read_csv_if_present(os.path.join(chosen, name))
        return df if df is not None else pd.DataFrame()

    return ComparisonBundle(
        path=chosen,
        latest_date=str(summary.get("latest_run_date", "")),
        prior_date=str(summary.get("prior_run_date", "")),
        summary=summary,
        score_movers=_csv("score_movers.csv"),
        band_changes=_csv("band_changes.csv"),
        quadrant_changes=_csv("quadrant_changes.csv"),
        action_flag_changes=_csv("action_flag_changes.csv"),
        new_funds=_csv("new_funds.csv"),
        removed_funds=_csv("removed_funds.csv"),
    )


def _load_model_overlay(run_path: str) -> Optional[ModelOverlayBundle]:
    """Load persisted model-holdings overlay artifacts for a run.

    Returns None when the overlay subdirectory is missing or does not contain
    a scorecard file (the canonical required artifact). All other files are
    optional — an absent file becomes an empty DataFrame so the packet can
    render the sections with clear placeholders.
    """
    out_dir = os.path.join(run_path, MODEL_OVERLAY_DIR)
    if not os.path.isdir(out_dir):
        return None
    scorecard_path = os.path.join(out_dir, OVERLAY_SCORECARD_FILE)
    if not os.path.isfile(scorecard_path):
        return None

    def _csv(name: str) -> pd.DataFrame:
        df = _read_csv_if_present(os.path.join(out_dir, name))
        return df if df is not None else pd.DataFrame()

    metadata = _read_json_if_present(os.path.join(out_dir, OVERLAY_METADATA_FILE)) or {}

    return ModelOverlayBundle(
        path=out_dir,
        summary=_csv(OVERLAY_SUMMARY_FILE),
        scorecard=_csv(OVERLAY_SCORECARD_FILE),
        current_review=_csv(OVERLAY_CURRENT_REVIEW_FILE),
        replacement_candidates=_csv(OVERLAY_REPLACEMENT_FILE),
        research_candidates=_csv(OVERLAY_RESEARCH_FILE),
        metadata=metadata,
    )


def load_packet_inputs(
    run_path: Optional[str] = None,
    run_date: Optional[str] = None,
    runs_dir: Optional[str] = None,
) -> PacketInputs:
    """Load the dual-score table and all optional supporting artifacts.

    Raises FileNotFoundError if no valid run archive can be resolved.
    """
    resolved = resolve_run_path(run_path=run_path, run_date=run_date, runs_dir=runs_dir)
    if resolved is None:
        hint = run_path or run_date or runs_dir or DEFAULT_RUNS_DIR
        raise FileNotFoundError(
            "Could not resolve a run archive. Tried: "
            f"run_path={run_path!r}, run_date={run_date!r}, runs_dir={runs_dir!r}. "
            f"Last location searched: {hint}. "
            "Create one with `python streamlit/run_archive.py create ...` or "
            "set FUND_PACKET_RUN_PATH to an existing run directory."
        )

    data_path = os.path.join(resolved, DATA_FILE)
    meta_path = os.path.join(resolved, METADATA_FILE)
    table = pd.read_csv(data_path)
    with open(meta_path) as f:
        metadata = json.load(f)

    validation = _read_json_if_present(os.path.join(resolved, VALIDATION_FILE))
    intake = _read_json_if_present(os.path.join(resolved, INTAKE_FILE))
    comparison = _load_comparison(resolved)
    model_overlay = _load_model_overlay(resolved)

    warnings: List[str] = []
    if validation is None:
        warnings.append("validation_report.json not found")
    if comparison is None:
        warnings.append("no comparison bundle found")
    if model_overlay is None:
        warnings.append("no model holdings overlay found")

    run_date_str = str(metadata.get("run_date") or os.path.basename(resolved))

    return PacketInputs(
        run_path=resolved,
        run_date=run_date_str,
        dual_score_table=table,
        metadata=metadata,
        validation=validation,
        intake=intake,
        comparison=comparison,
        model_overlay=model_overlay,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Derived views
# ---------------------------------------------------------------------------

_BAND_ORDER = ["STRONG", "REVIEW", "WEAK"]


def _present_columns(df: pd.DataFrame, cols: List[str]) -> List[str]:
    return [c for c in cols if c in df.columns]


def top_by_score(
    table: pd.DataFrame,
    score_col: str,
    top_n: int = 50,
) -> pd.DataFrame:
    """Return the top-N rows by `score_col`, dropping NaNs in that column."""
    if score_col not in table.columns:
        return pd.DataFrame()
    sub = table.dropna(subset=[score_col])
    sort_cols = [score_col, "Symbol"] if "Symbol" in sub.columns else [score_col]
    ascending = [False, True] if "Symbol" in sub.columns else [False]
    out = (
        sub.sort_values(sort_cols, ascending=ascending, kind="stable")
        .head(top_n)
        .reset_index(drop=True)
    )
    out.index = out.index + 1
    out.index.name = "Rank"
    return out


def top_by_consensus(table: pd.DataFrame, top_n: int = 50) -> pd.DataFrame:
    """Top-N by `Consensus_Rank` (ascending = best).

    Falls back to the mean of Score_2023_Final and Score_2025_Final when
    `Consensus_Rank` is absent.
    """
    if "Consensus_Rank" in table.columns:
        sub = table.dropna(subset=["Consensus_Rank"])
        sort_cols = ["Consensus_Rank", "Symbol"] if "Symbol" in sub.columns else ["Consensus_Rank"]
        ascending = [True, True] if "Symbol" in sub.columns else [True]
        out = (
            sub.sort_values(sort_cols, ascending=ascending, kind="stable")
            .head(top_n)
            .reset_index(drop=True)
        )
    elif {"Score_2023_Final", "Score_2025_Final"}.issubset(table.columns):
        tmp = table.dropna(subset=["Score_2023_Final", "Score_2025_Final"]).copy()
        tmp["Consensus_Score"] = (tmp["Score_2023_Final"] + tmp["Score_2025_Final"]) / 2.0
        sort_cols = ["Consensus_Score", "Symbol"] if "Symbol" in tmp.columns else ["Consensus_Score"]
        ascending = [False, True] if "Symbol" in tmp.columns else [False]
        out = (
            tmp.sort_values(sort_cols, ascending=ascending, kind="stable")
            .head(top_n)
            .reset_index(drop=True)
        )
    else:
        return pd.DataFrame()
    out.index = out.index + 1
    out.index.name = "Rank"
    return out


def disagreement_list(table: pd.DataFrame, min_gap: float = 10.0) -> pd.DataFrame:
    """Funds whose 2023 and 2025 views disagree meaningfully.

    Disagree = |Score_Gap| >= `min_gap` OR Score_Band_2023 != Score_Band_2025.
    """
    required = {"Score_2023_Final", "Score_2025_Final"}
    if not required.issubset(table.columns):
        return pd.DataFrame()
    df = table.dropna(subset=list(required)).copy()
    if df.empty:
        return df

    gap_col = df["Score_Gap"] if "Score_Gap" in df.columns else (
        df["Score_2025_Final"] - df["Score_2023_Final"]
    )
    mask_gap = gap_col.abs() >= min_gap

    if {"Score_Band_2023", "Score_Band_2025"}.issubset(df.columns):
        mask_band = df["Score_Band_2023"] != df["Score_Band_2025"]
    else:
        mask_band = pd.Series(False, index=df.index)

    out = df[mask_gap | mask_band].copy()
    if "Score_Gap" not in out.columns:
        out["Score_Gap"] = gap_col[mask_gap | mask_band]
    out = out.assign(_abs_gap=out["Score_Gap"].abs())
    sort_cols = ["_abs_gap", "Symbol"] if "Symbol" in out.columns else ["_abs_gap"]
    ascending = [False, True] if "Symbol" in out.columns else [False]
    return (
        out.sort_values(sort_cols, ascending=ascending, kind="stable")
        .drop(columns="_abs_gap")
        .reset_index(drop=True)
    )


def dual_lens_matrix(table: pd.DataFrame) -> pd.DataFrame:
    """3x3 band-vs-band count matrix (rows=2025 band, cols=2023 band)."""
    needed = {"Score_Band_2023", "Score_Band_2025"}
    if not needed.issubset(table.columns):
        return pd.DataFrame()
    df = table.dropna(subset=list(needed))
    if df.empty:
        return pd.DataFrame(index=_BAND_ORDER, columns=_BAND_ORDER).fillna(0).astype(int)
    return (
        pd.crosstab(df["Score_Band_2025"], df["Score_Band_2023"], dropna=False)
        .reindex(index=_BAND_ORDER, columns=_BAND_ORDER)
        .fillna(0)
        .astype(int)
    )


def quadrant_counts(table: pd.DataFrame) -> pd.Series:
    if "Quadrant" not in table.columns:
        return pd.Series(dtype=int)
    return table["Quadrant"].value_counts(dropna=False).sort_index()


# ---------------------------------------------------------------------------
# Convenience metadata helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Model-overlay derived views
# ---------------------------------------------------------------------------

# Overlay action-flag weight columns produced by streamlit/model_holdings_overlay.py.
# Ordered from best-to-worst so committee stacks read naturally top-to-bottom.
OVERLAY_WEIGHT_COLUMNS = [
    ("Weight_Pct_HighConviction", "High Conviction Hold"),
    ("Weight_Pct_PerfLed", "Performance-Led / Review Quality"),
    ("Weight_Pct_QualityLed", "Quality-Led / Review Patience"),
    ("Weight_Pct_Replacement", "Replacement Candidate"),
    ("Weight_Pct_Unscored", "Unscored / Coverage Gap"),
]

# Known share-class reconciliations the overlay applies silently before the
# join. Surfacing these in the packet makes alias behavior visible to the
# committee without them having to open the config file.
KNOWN_ALIASES = [
    ("PRBLX", "PRILX", "Parnassus Core Equity — kept institutional share class"),
    ("GSTKX", "GSIKX", "GS Small Cap Growth Insights — kept institutional share class"),
    ("PONPX", "PIMIX", "PIMCO Income — kept institutional share class"),
    ("FECMX", "FEMKX", "Fidelity Emerging Markets — kept oldest share class"),
]


def model_stackup(summary: pd.DataFrame) -> pd.DataFrame:
    """Compact committee-facing view of the per-model summary table.

    Returns an empty DataFrame if ``summary`` is empty. Columns not present in
    the summary are silently omitted so this is tolerant of older runs that
    may be missing individual weight columns.
    """
    if summary is None or summary.empty:
        return pd.DataFrame()
    wanted = [
        "Model_Name",
        "Holding_Count",
        "Scored_Holding_Count",
        "Scored_Weight_Pct",
        "Weighted_Score_2023",
        "Weighted_Score_2025",
        "Weight_Pct_Q1_Both_Strong",
        "Weight_Pct_Q4_Both_Weak",
        "Weight_Pct_HighConviction",
        "Weight_Pct_Replacement",
        "Weight_Pct_Unscored",
    ]
    cols = [c for c in wanted if c in summary.columns]
    view = summary[cols].copy()
    # Round numeric columns for display; keep ints intact.
    for c in view.columns:
        if view[c].dtype.kind in "fc":
            view[c] = view[c].round(1)
    return view.reset_index(drop=True)


def action_flag_weight_matrix(summary: pd.DataFrame) -> pd.DataFrame:
    """Model-by-action-flag matrix of weight share (%) suitable for a stacked bar.

    Rows = Model_Name, columns = action-flag labels, values = weight %.
    """
    if summary is None or summary.empty or "Model_Name" not in summary.columns:
        return pd.DataFrame()
    present_cols = [(c, label) for c, label in OVERLAY_WEIGHT_COLUMNS if c in summary.columns]
    if not present_cols:
        return pd.DataFrame()
    out = pd.DataFrame({"Model_Name": summary["Model_Name"]})
    for col, label in present_cols:
        out[label] = summary[col].astype(float).round(1)
    return out.set_index("Model_Name")


def weak_holdings(current_review: pd.DataFrame, top_n: int = 30) -> pd.DataFrame:
    """Holdings flagged for replacement or coverage review, trimmed for committee.

    Filters to the rows most likely to drive discussion (Replacement_Candidate
    first, then Review_Missing_Score), and limits to ``top_n`` rows.
    """
    if current_review is None or current_review.empty:
        return pd.DataFrame()
    df = current_review.copy()
    wanted = [
        "Model_Name", "Symbol", "Scoring_Symbol", "Name", "Category",
        "Target_Weight_Pct",
        "Score_2023_Final", "Score_2025_Final",
        "Score_Band_2023", "Score_Band_2025",
        "Overlay_Action", "Primary_Driver",
    ]
    cols = [c for c in wanted if c in df.columns]
    view = df[cols].copy()
    for c in ("Score_2023_Final", "Score_2025_Final", "Target_Weight_Pct"):
        if c in view.columns:
            view[c] = view[c].round(1)
    return view.head(top_n).reset_index(drop=True)


def replacement_candidates_for_committee(
    replacements: pd.DataFrame,
    top_per_holding: int = 3,
) -> pd.DataFrame:
    """Trim the raw replacement_candidates table for packet display."""
    if replacements is None or replacements.empty:
        return pd.DataFrame()
    df = replacements.copy()
    if "Candidate_Rank" in df.columns:
        df = df[df["Candidate_Rank"] <= top_per_holding]
    wanted = [
        "Model_Name", "Current_Symbol", "Current_Name", "Current_Category",
        "Current_Score_2023_Final", "Current_Score_2025_Final",
        "Candidate_Rank", "Candidate_Symbol", "Candidate_Name",
        "Candidate_Fund_Type",
        "Candidate_Score_2023_Final", "Candidate_Score_2025_Final",
        "Candidate_Score_Band_2023", "Candidate_Score_Band_2025",
    ]
    cols = [c for c in wanted if c in df.columns]
    view = df[cols].copy()
    for c in (
        "Current_Score_2023_Final", "Current_Score_2025_Final",
        "Candidate_Score_2023_Final", "Candidate_Score_2025_Final",
    ):
        if c in view.columns:
            view[c] = view[c].round(1)
    return view.reset_index(drop=True)


def research_candidates_for_committee(
    research: pd.DataFrame,
    top_n: int = 25,
) -> pd.DataFrame:
    """Trim the research candidates table for packet display."""
    if research is None or research.empty:
        return pd.DataFrame()
    wanted = [
        "Symbol", "Name", "Category", "Fund_Type",
        "Score_2023_Final", "Score_2025_Final",
        "Rank_2023", "Rank_2025", "Consensus_Rank",
        "Score_Band_2023", "Score_Band_2025", "Quadrant",
        "Primary_Driver",
    ]
    cols = [c for c in wanted if c in research.columns]
    view = research[cols].head(top_n).copy()
    for c in ("Score_2023_Final", "Score_2025_Final"):
        if c in view.columns:
            view[c] = view[c].round(1)
    return view.reset_index(drop=True)


def alias_notes(overlay_metadata: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Return alias-pair notes for committee display.

    Merges the aliases actually observed in this run (from overlay metadata)
    with the KNOWN_ALIASES rationale table. Only returns entries that apply
    to this run — if ``overlay_metadata`` lacks ``alias_pairs`` the result is
    empty, so absence is rendered cleanly in the packet.
    """
    if not overlay_metadata:
        return []
    pairs = overlay_metadata.get("alias_pairs") or []
    rationale = {orig: (scoring, note) for orig, scoring, note in KNOWN_ALIASES}
    notes: List[Dict[str, str]] = []
    for p in pairs:
        orig = str(p.get("original", "")).upper()
        scoring = str(p.get("scoring", "")).upper()
        if not orig or not scoring:
            continue
        reason = ""
        if orig in rationale and rationale[orig][0].upper() == scoring:
            reason = rationale[orig][1]
        notes.append({"original": orig, "scoring": scoring, "reason": reason})
    return notes


def metadata_banner(metadata: Dict[str, Any]) -> Dict[str, str]:
    """Small dict of scalar fields safe to display in a header banner."""
    inputs = metadata.get("inputs", {}) or {}
    p25 = (inputs.get("path_2025") or {}).get("basename")
    p23 = (inputs.get("path_2023") or {}).get("basename")
    return {
        "run_date": str(metadata.get("run_date", "unknown")),
        "generated_at": str(metadata.get("generated_at", "unknown")),
        "score_system": str(metadata.get("score_system", "unknown")),
        "input_2025": str(p25) if p25 else "—",
        "input_2023": str(p23) if p23 else "—",
        "notes": str(metadata.get("notes") or ""),
    }


__all__ = [
    "PacketInputs",
    "ComparisonBundle",
    "ModelOverlayBundle",
    "resolve_run_path",
    "load_packet_inputs",
    "top_by_score",
    "top_by_consensus",
    "disagreement_list",
    "dual_lens_matrix",
    "quadrant_counts",
    "metadata_banner",
    "model_stackup",
    "action_flag_weight_matrix",
    "weak_holdings",
    "replacement_candidates_for_committee",
    "research_candidates_for_committee",
    "alias_notes",
    "OVERLAY_WEIGHT_COLUMNS",
    "KNOWN_ALIASES",
]
