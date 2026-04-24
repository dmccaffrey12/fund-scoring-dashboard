"""
workflow_ui
===========
Helper functions for the Streamlit "Monthly Workflow" page. The page lets a
portfolio manager operate the full month-end pipeline without shell access:

    upload paired YCharts CSVs (2025 + 2023)
        -> intake validation (ycharts_intake)
        -> dual-score table (dual_score_table)
        -> dated run archive (run_archive)
        -> previews of Top-50 2023/2025/Consensus + Disagreement
        -> optional latest-vs-prior comparison (run_comparison)
        -> Excel audit workbook download (excel_audit_export)

The functions in this module are deliberately UI-free (they return data and
file paths, not Streamlit widgets) so they can be unit-tested without a
running Streamlit server.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from dual_score_table import build_dual_score_table
from excel_audit_export import export_run
from model_holdings_intake import (
    summarize as summarize_model_holdings,
    validate_model_holdings_dataframe,
    validate_model_holdings_file,
)
from model_holdings_overlay import (
    OverlayResult,
    build_model_overlay,
    load_overlay,
    write_overlay,
)
from replacement_workbench import (
    DEFAULT_TOP_N as REPLACEMENT_DEFAULT_TOP_N,
    ReplacementResult,
    build_replacement_workbench,
    load_replacement,
    workbench_dir,
    write_replacement,
)
from symbol_aliases import load_default_aliases
from run_archive import (
    DEFAULT_RUNS_DIR,
    create_run_archive,
    list_runs,
    load_latest_run,
    load_run,
    run_overlay_dir,
)
from run_comparison import (
    InsufficientRunsError,
    run_comparison,
)
from ycharts_intake import summarize, validate_pair


# ---------------------------------------------------------------------------
# Upload handling
# ---------------------------------------------------------------------------

def persist_uploads(
    file_2025_bytes: bytes,
    file_2023_bytes: bytes,
    dest_dir: Optional[str] = None,
) -> Tuple[str, str, str]:
    """Write in-memory uploaded file bytes to disk and return their paths.

    Returns (path_2025, path_2023, tmp_dir). The caller is responsible for
    cleaning up the returned ``tmp_dir`` (e.g. via ``shutil.rmtree``) when
    done — unless ``dest_dir`` was supplied (in which case it's returned
    as-is and not managed here).
    """
    tmp_dir = dest_dir or tempfile.mkdtemp(prefix="fundscore_upload_")
    path_2025 = os.path.join(tmp_dir, "ycharts_2025.csv")
    path_2023 = os.path.join(tmp_dir, "ycharts_2023.csv")
    with open(path_2025, "wb") as f:
        f.write(file_2025_bytes)
    with open(path_2023, "wb") as f:
        f.write(file_2023_bytes)
    return path_2025, path_2023, tmp_dir


def cleanup_tmp(tmp_dir: Optional[str]) -> None:
    if tmp_dir and os.path.isdir(tmp_dir):
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Intake validation
# ---------------------------------------------------------------------------

def run_intake(
    path_2025: str,
    path_2023: str,
) -> Dict[str, Any]:
    """Run YCharts intake validation on a paired upload.

    Returns the full pair report dict (see ``ycharts_intake.validate_pair``)
    with an extra ``"summary_text"`` field holding the human-readable form.
    """
    report = validate_pair(path_2025=path_2025, path_2023=path_2023)
    report["summary_text"] = summarize(report)
    return report


# ---------------------------------------------------------------------------
# Archive + table
# ---------------------------------------------------------------------------

def create_archive_from_uploads(
    path_2025: str,
    path_2023: str,
    run_date: str,
    runs_dir: str = DEFAULT_RUNS_DIR,
    overwrite: bool = False,
    preflight: str = "warn",
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the dual-score table and persist a run archive.

    Returns the dict produced by ``run_archive.load_run`` so callers can
    immediately render previews, validation, etc.
    """
    table = build_dual_score_table(
        path_2025=path_2025,
        path_2023=path_2023,
        how="inner",
    )
    create_run_archive(
        run_date=run_date,
        runs_dir=runs_dir,
        path_2025=path_2025,
        path_2023=path_2023,
        table=table,
        overwrite=overwrite,
        preflight=preflight,
        notes=notes,
    )
    return load_run(run_date, runs_dir=runs_dir)


# ---------------------------------------------------------------------------
# Previews from a dual-score table
# ---------------------------------------------------------------------------

TOP_N_DEFAULT = 50

PREVIEW_COLUMNS = [
    "Symbol", "Name", "Category", "Fund_Type",
    "Score_2023_Final", "Score_2025_Final", "Score_Gap",
    "Rank_2023", "Rank_2025", "Consensus_Rank",
    "Score_Band_2023", "Score_Band_2025", "Quadrant",
    "Action_Flag",
]


def _present_cols(df: pd.DataFrame) -> list:
    return [c for c in PREVIEW_COLUMNS if c in df.columns]


def top_previews(
    table: pd.DataFrame,
    top_n: int = TOP_N_DEFAULT,
) -> Dict[str, pd.DataFrame]:
    """Return preview DataFrames: top50_2023, top50_2025, top50_consensus, disagreement."""
    cols = _present_cols(table)
    out: Dict[str, pd.DataFrame] = {}

    if "Score_2023_Final" in table.columns:
        out["top_2023"] = (
            table.sort_values("Score_2023_Final", ascending=False, na_position="last")
                 .head(top_n)[cols]
                 .reset_index(drop=True)
        )
    else:
        out["top_2023"] = pd.DataFrame(columns=cols)

    if "Score_2025_Final" in table.columns:
        out["top_2025"] = (
            table.sort_values("Score_2025_Final", ascending=False, na_position="last")
                 .head(top_n)[cols]
                 .reset_index(drop=True)
        )
    else:
        out["top_2025"] = pd.DataFrame(columns=cols)

    if "Consensus_Rank" in table.columns:
        out["top_consensus"] = (
            table.sort_values("Consensus_Rank", ascending=True, na_position="last")
                 .head(top_n)[cols]
                 .reset_index(drop=True)
        )
    else:
        out["top_consensus"] = pd.DataFrame(columns=cols)

    if "Score_Gap" in table.columns:
        disagree = table[table["Score_Gap"].notna()].copy()
        disagree["_abs_gap"] = disagree["Score_Gap"].abs()
        out["disagreement"] = (
            disagree.sort_values("_abs_gap", ascending=False)
                    .drop(columns=["_abs_gap"])
                    .head(top_n)[cols]
                    .reset_index(drop=True)
        )
    else:
        out["disagreement"] = pd.DataFrame(columns=cols)

    return out


# ---------------------------------------------------------------------------
# Archive listing
# ---------------------------------------------------------------------------

def available_runs(runs_dir: str = DEFAULT_RUNS_DIR) -> list:
    return list_runs(runs_dir=runs_dir)


def load_latest(runs_dir: str = DEFAULT_RUNS_DIR) -> Optional[Dict[str, Any]]:
    try:
        return load_latest_run(runs_dir=runs_dir)
    except FileNotFoundError:
        return None


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def maybe_compare(
    runs_dir: str = DEFAULT_RUNS_DIR,
    write: bool = True,
) -> Optional[Dict[str, Any]]:
    """Compare the latest run with its immediate predecessor, if available.

    Returns None when fewer than two runs exist. Returns a dict with the
    ComparisonResult fields flattened into plain DataFrames so the page can
    render tables directly.
    """
    runs = list_runs(runs_dir=runs_dir)
    if len(runs) < 2:
        return None
    try:
        result, paths = run_comparison(runs_dir=runs_dir, write=write)
    except InsufficientRunsError:
        return None
    return {
        "latest_date": result.latest_date,
        "prior_date": result.prior_date,
        "summary": result.summary,
        "tables": result.tables(),
        "paths": paths,
    }


# ---------------------------------------------------------------------------
# Excel audit export
# ---------------------------------------------------------------------------

def build_audit_workbook_bytes(
    run_date: str,
    runs_dir: str = DEFAULT_RUNS_DIR,
    include_comparison: bool = True,
) -> Tuple[str, bytes]:
    """Render the Excel audit workbook and return (filename, bytes).

    Writes to a temporary path so we can reuse ``export_run`` as-is, then
    reads the bytes back for a Streamlit download button.
    """
    with tempfile.TemporaryDirectory(prefix="fundscore_xlsx_") as tmp:
        target = os.path.join(tmp, f"fund_scoring_audit_{run_date}.xlsx")
        export_run(
            run_date=run_date,
            runs_dir=runs_dir,
            out_path=target,
            include_comparison=include_comparison,
        )
        with open(target, "rb") as f:
            data = f.read()
    return (f"fund_scoring_audit_{run_date}.xlsx", data)


# ---------------------------------------------------------------------------
# Model holdings overlay (optional)
# ---------------------------------------------------------------------------

def persist_model_holdings_upload(
    file_bytes: bytes,
    dest_dir: Optional[str] = None,
) -> Tuple[str, str]:
    """Write uploaded model-holdings CSV bytes to disk.

    Returns (path, tmp_dir). Caller owns ``tmp_dir`` unless ``dest_dir``
    was supplied.
    """
    tmp_dir = dest_dir or tempfile.mkdtemp(prefix="fundscore_models_")
    path = os.path.join(tmp_dir, "model_holdings.csv")
    with open(path, "wb") as f:
        f.write(file_bytes)
    return path, tmp_dir


def run_model_holdings_intake(
    holdings_path: str,
    dual_table: Optional[pd.DataFrame] = None,
    alias_csv_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate a model-holdings CSV against the universe in ``dual_table``.

    Returns the intake report dict with an extra ``summary_text`` field.
    Share-class aliases are applied before the coverage check.
    """
    dual_symbols = None
    if dual_table is not None and "Symbol" in dual_table.columns:
        dual_symbols = dual_table["Symbol"].dropna().astype(str).tolist()
    alias_map = load_default_aliases(extra_path=alias_csv_path)
    report = validate_model_holdings_file(
        holdings_path, dual_score_symbols=dual_symbols, alias_map=alias_map,
    )
    report["summary_text"] = summarize_model_holdings(report)
    return report


def generate_model_overlay_for_run(
    holdings_path: str,
    run_date: str,
    runs_dir: str = DEFAULT_RUNS_DIR,
    persist: bool = True,
    alias_csv_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the overlay for the specified run and (optionally) persist it.

    The returned dict has the same shape as ``load_overlay`` plus an
    ``OverlayResult`` object under ``"result"``.
    """
    run = load_run(run_date, runs_dir=runs_dir)
    holdings_df = pd.read_csv(holdings_path)
    alias_map = load_default_aliases(extra_path=alias_csv_path)
    result = build_model_overlay(holdings_df, run["table"], alias_map=alias_map)

    out_dir = run_overlay_dir(runs_dir, run_date)
    paths: Dict[str, str] = {}
    if persist:
        paths = write_overlay(result, out_dir)

    return {
        "run_date": run_date,
        "path": out_dir,
        "paths": paths,
        "result": result,
        "scorecard": result.scorecard,
        "summary": result.summary,
        "current_review": result.current_review,
        "research_candidates": result.research_candidates,
        "replacement_candidates": result.replacement_candidates,
        "metadata": result.metadata,
    }


def load_model_overlay_for_run(
    run_date: str,
    runs_dir: str = DEFAULT_RUNS_DIR,
) -> Optional[Dict[str, Any]]:
    """Return persisted overlay artifacts for the run, or None if absent."""
    out_dir = run_overlay_dir(runs_dir, run_date)
    return load_overlay(out_dir)


# ---------------------------------------------------------------------------
# Replacement Workbench (optional, per-ticker replacement research)
# ---------------------------------------------------------------------------

def model_holding_symbols_for_run(
    run_date: str,
    runs_dir: str = DEFAULT_RUNS_DIR,
) -> pd.DataFrame:
    """Return a small {Symbol, Scoring_Symbol, Model_Name, Target_Weight_Pct}
    frame pulled from the overlay scorecard for ``run_date`` — used by the
    replacement workbench UI to populate its 'current holding' picker.

    Returns an empty DataFrame when no overlay has been generated yet.
    """
    cols = ["Symbol", "Scoring_Symbol", "Model_Name", "Target_Weight_Pct",
            "Name", "Category", "Overlay_Action"]
    overlay = load_overlay(run_overlay_dir(runs_dir, run_date))
    if overlay is None:
        return pd.DataFrame(columns=cols)
    sc = overlay.get("scorecard")
    if sc is None or sc.empty:
        return pd.DataFrame(columns=cols)
    present = [c for c in cols if c in sc.columns]
    return sc[present].copy()


def generate_replacement_workbench_for_run(
    run_date: str,
    ticker: str,
    runs_dir: str = DEFAULT_RUNS_DIR,
    model_name: Optional[str] = None,
    category_override: Optional[str] = None,
    top_n: int = REPLACEMENT_DEFAULT_TOP_N,
    exclude_held: bool = False,
    persist: bool = True,
    alias_csv_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Build + (optionally) persist a replacement short list for one ticker.

    When an overlay has already been generated for the run the scorecard is
    loaded automatically so candidates can flag ``Already_Held`` and the
    current-holding profile can surface the Model_Name / Target_Weight_Pct.
    """
    run = load_run(run_date, runs_dir=runs_dir)
    scorecard: Optional[pd.DataFrame] = None
    overlay = load_overlay(run_overlay_dir(runs_dir, run_date))
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
    )

    out_dir = workbench_dir(runs_dir, run_date, ticker)
    paths: Dict[str, str] = {}
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


def load_replacement_for_run(
    run_date: str,
    ticker: str,
    runs_dir: str = DEFAULT_RUNS_DIR,
) -> Optional[Dict[str, Any]]:
    """Return persisted workbench artifacts for the run/ticker, or None."""
    out_dir = workbench_dir(runs_dir, run_date, ticker)
    return load_replacement(out_dir)


# ---------------------------------------------------------------------------
# Quarto packet (optional)
# ---------------------------------------------------------------------------

def find_packet_html(
    repo_root: Optional[str] = None,
) -> Optional[str]:
    """Return the path to a pre-rendered monthly packet HTML, if one exists."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = repo_root or os.path.abspath(os.path.join(here, ".."))
    candidate = os.path.join(root, "reports", "monthly_packet", "monthly_packet.html")
    return candidate if os.path.isfile(candidate) else None
