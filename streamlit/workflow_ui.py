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
from run_archive import (
    DEFAULT_RUNS_DIR,
    create_run_archive,
    list_runs,
    load_latest_run,
    load_run,
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
