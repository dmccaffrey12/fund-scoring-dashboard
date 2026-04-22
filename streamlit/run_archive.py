"""
Run Archive
===========
Durable local archive convention for fund scoring runs.

A "run" is a dated snapshot of the canonical dual-score table plus the
metadata and validation context needed to reproduce or audit it. Each run
lives in its own folder under `streamlit/runs/YYYY-MM-DD/` and contains:

    data/dual_score_table.csv       — canonical output from PR 3
    metadata/run_metadata.json      — run date, timestamp, inputs, hashes
    validation/validation_report.json — row/coverage/band/quadrant counts

A `runs/latest.json` manifest file (not a symlink — portable across OSes)
points at the most recent run directory by name.

This archive format is the substrate for the planned month-over-month
"What Changed" view and the Excel 2019 audit export.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
from typing import Any, Dict, List, Optional

import pandas as pd

from dual_score_table import (
    DEFAULT_2023_PATH,
    DEFAULT_2025_PATH,
    build_dual_score_table,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RUNS_DIR = os.path.join(_HERE, "runs")
LATEST_MANIFEST_NAME = "latest.json"

RUN_LAYOUT = {
    "data": "data",
    "metadata": "metadata",
    "validation": "validation",
}
DUAL_TABLE_NAME = "dual_score_table.csv"
METADATA_NAME = "run_metadata.json"
VALIDATION_NAME = "validation_report.json"

SCORE_SYSTEM_VERSION = "dual-2023-combined+2025-split"


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------

def _file_sha256(path: str) -> Optional[str]:
    if not path or not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _describe_input(path: str) -> Dict[str, Any]:
    return {
        "path": path,
        "basename": os.path.basename(path) if path else None,
        "exists": bool(path) and os.path.isfile(path),
        "size_bytes": os.path.getsize(path) if path and os.path.isfile(path) else None,
        "sha256": _file_sha256(path),
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def build_validation_report(table: pd.DataFrame) -> Dict[str, Any]:
    """Compute the validation counters stored alongside each run."""
    def _value_counts(col: str) -> Dict[str, int]:
        if col not in table.columns:
            return {}
        return {str(k): int(v) for k, v in table[col].value_counts(dropna=False).items()}

    def _score_summary(col: str) -> Dict[str, Optional[float]]:
        if col not in table.columns:
            return {"min": None, "max": None, "mean": None, "missing": None}
        series = table[col]
        return {
            "min": float(series.min()) if series.notna().any() else None,
            "max": float(series.max()) if series.notna().any() else None,
            "mean": float(series.mean()) if series.notna().any() else None,
            "missing": int(series.isna().sum()),
        }

    def _coverage_summary(col: str) -> Dict[str, Optional[float]]:
        if col not in table.columns:
            return {"mean": None, "min": None, "missing": None}
        series = table[col]
        return {
            "mean": float(series.mean()) if series.notna().any() else None,
            "min": float(series.min()) if series.notna().any() else None,
            "missing": int(series.isna().sum()),
        }

    has_both = int(
        table[["Score_2023_Final", "Score_2025_Final"]]
        .notna()
        .all(axis=1)
        .sum()
    ) if {"Score_2023_Final", "Score_2025_Final"}.issubset(table.columns) else 0

    return {
        "row_count": int(len(table)),
        "joined_count": has_both,
        "missing_score_2023": int(table["Score_2023_Final"].isna().sum())
            if "Score_2023_Final" in table.columns else None,
        "missing_score_2025": int(table["Score_2025_Final"].isna().sum())
            if "Score_2025_Final" in table.columns else None,
        "score_2023": _score_summary("Score_2023_Final"),
        "score_2025": _score_summary("Score_2025_Final"),
        "score_gap": _score_summary("Score_Gap"),
        "band_counts_2023": _value_counts("Score_Band_2023"),
        "band_counts_2025": _value_counts("Score_Band_2025"),
        "quadrant_counts": _value_counts("Quadrant"),
        "action_flag_counts": _value_counts("Action_Flag"),
        "fund_type_counts": _value_counts("Fund_Type"),
        "coverage_2023": _coverage_summary("Data_Coverage_2023"),
        "coverage_2025": _coverage_summary("Data_Coverage_2025"),
    }


# ---------------------------------------------------------------------------
# Archive creation
# ---------------------------------------------------------------------------

def _resolve_run_date(run_date: Optional[str]) -> str:
    if run_date is None:
        return dt.date.today().isoformat()
    # Validate format to catch fat-fingered CLI inputs early.
    dt.date.fromisoformat(run_date)
    return run_date


def _run_dir(runs_dir: str, run_date: str) -> str:
    return os.path.join(runs_dir, run_date)


def create_run_archive(
    run_date: Optional[str] = None,
    runs_dir: str = DEFAULT_RUNS_DIR,
    path_2025: str = DEFAULT_2025_PATH,
    path_2023: str = DEFAULT_2023_PATH,
    how: str = "inner",
    table: Optional[pd.DataFrame] = None,
    notes: Optional[str] = None,
    overwrite: bool = False,
    update_latest: bool = True,
    preflight: str = "off",
) -> str:
    """
    Create a dated run archive and return the directory path.

    If `table` is supplied it is used verbatim (useful for tests and for
    archiving a pre-built DataFrame). Otherwise the table is built from the
    supplied input paths via `build_dual_score_table`.

    `preflight` controls whether the raw YCharts exports are validated
    before the dual-score table is built:
        "off"    — skip validation (default)
        "warn"   — run validation, persist the report, never raise
        "strict" — run validation, raise ValueError on any error finding

    The intake report (when run) is written to
    `validation/intake_report.json` alongside the usual validation file.
    """
    resolved_date = _resolve_run_date(run_date)
    target = _run_dir(runs_dir, resolved_date)

    if os.path.exists(target):
        if not overwrite:
            raise FileExistsError(
                f"Run archive already exists: {target}. Pass overwrite=True "
                "or choose a different --run-date."
            )
        shutil.rmtree(target)

    for sub in RUN_LAYOUT.values():
        os.makedirs(os.path.join(target, sub), exist_ok=True)

    intake_report: Optional[Dict[str, Any]] = None
    intake_report_path: Optional[str] = None
    if preflight != "off" and table is None:
        from ycharts_intake import preflight_for_archive  # local import
        intake_report = preflight_for_archive(
            path_2025=path_2025,
            path_2023=path_2023,
            strict=(preflight == "strict"),
        )
        intake_report_path = os.path.join(
            target, RUN_LAYOUT["validation"], "intake_report.json"
        )
        with open(intake_report_path, "w") as f:
            json.dump(intake_report, f, indent=2, sort_keys=True, default=str)

    if table is None:
        table = build_dual_score_table(
            path_2025=path_2025,
            path_2023=path_2023,
            how=how,
        )

    data_path = os.path.join(target, RUN_LAYOUT["data"], DUAL_TABLE_NAME)
    table.to_csv(data_path, index=False)

    validation = build_validation_report(table)
    validation_path = os.path.join(target, RUN_LAYOUT["validation"], VALIDATION_NAME)
    with open(validation_path, "w") as f:
        json.dump(validation, f, indent=2, sort_keys=True)

    metadata = {
        "run_date": resolved_date,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "score_system": SCORE_SYSTEM_VERSION,
        "join_how": how,
        "inputs": {
            "path_2025": _describe_input(path_2025),
            "path_2023": _describe_input(path_2023),
        },
        "outputs": {
            "dual_score_table": {
                "relative_path": os.path.relpath(data_path, target),
                "row_count": int(len(table)),
                "column_count": int(table.shape[1]),
                "columns": list(table.columns),
                "sha256": _file_sha256(data_path),
            },
            "validation_report": {
                "relative_path": os.path.relpath(validation_path, target),
                "sha256": _file_sha256(validation_path),
            },
        },
        "notes": notes,
        "preflight": {
            "mode": preflight,
            "ran": intake_report is not None,
            "failed": bool(intake_report and intake_report.get("failed")),
            "report_relative_path": (
                os.path.relpath(intake_report_path, target)
                if intake_report_path else None
            ),
        },
    }
    metadata_path = os.path.join(target, RUN_LAYOUT["metadata"], METADATA_NAME)
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2, sort_keys=True)

    if update_latest:
        write_latest_manifest(runs_dir, resolved_date)

    return target


def write_latest_manifest(runs_dir: str, run_date: str) -> str:
    """
    Write `runs/latest.json` pointing at `run_date`.

    We use a manifest file rather than a symlink because symlinks are
    unreliable on Windows without elevated perms and interact poorly with
    some CI runners / file syncers.
    """
    os.makedirs(runs_dir, exist_ok=True)
    manifest_path = os.path.join(runs_dir, LATEST_MANIFEST_NAME)
    payload = {
        "run_date": run_date,
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "relative_path": run_date,
    }
    with open(manifest_path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    return manifest_path


# ---------------------------------------------------------------------------
# History / retrieval
# ---------------------------------------------------------------------------

def _is_run_dir(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    name = os.path.basename(path.rstrip(os.sep))
    try:
        dt.date.fromisoformat(name)
    except ValueError:
        return False
    return os.path.isfile(os.path.join(path, RUN_LAYOUT["metadata"], METADATA_NAME))


def list_runs(runs_dir: str = DEFAULT_RUNS_DIR) -> List[str]:
    """Return run dates (YYYY-MM-DD) sorted oldest → newest."""
    if not os.path.isdir(runs_dir):
        return []
    dates: List[str] = []
    for name in os.listdir(runs_dir):
        full = os.path.join(runs_dir, name)
        if _is_run_dir(full):
            dates.append(name)
    return sorted(dates)


def _read_json(path: str) -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def load_run(
    run_date: str,
    runs_dir: str = DEFAULT_RUNS_DIR,
) -> Dict[str, Any]:
    """Return a dict with the dual-score DataFrame, metadata, and validation."""
    target = _run_dir(runs_dir, run_date)
    if not _is_run_dir(target):
        raise FileNotFoundError(f"No run archive found at {target}")
    data_path = os.path.join(target, RUN_LAYOUT["data"], DUAL_TABLE_NAME)
    meta_path = os.path.join(target, RUN_LAYOUT["metadata"], METADATA_NAME)
    val_path = os.path.join(target, RUN_LAYOUT["validation"], VALIDATION_NAME)
    return {
        "run_date": run_date,
        "path": target,
        "table": pd.read_csv(data_path),
        "metadata": _read_json(meta_path),
        "validation": _read_json(val_path),
    }


def _latest_date_from_manifest(runs_dir: str) -> Optional[str]:
    manifest = os.path.join(runs_dir, LATEST_MANIFEST_NAME)
    if not os.path.isfile(manifest):
        return None
    try:
        payload = _read_json(manifest)
    except json.JSONDecodeError:
        return None
    candidate = payload.get("run_date")
    if candidate and _is_run_dir(_run_dir(runs_dir, candidate)):
        return candidate
    return None


def load_latest_run(runs_dir: str = DEFAULT_RUNS_DIR) -> Dict[str, Any]:
    """Load the newest run, preferring the manifest but falling back to the
    lexicographic maximum of valid dated folders."""
    latest = _latest_date_from_manifest(runs_dir)
    if latest is None:
        runs = list_runs(runs_dir)
        if not runs:
            raise FileNotFoundError(f"No runs found under {runs_dir}")
        latest = runs[-1]
    return load_run(latest, runs_dir=runs_dir)


def load_prior_run(
    run_date: str,
    runs_dir: str = DEFAULT_RUNS_DIR,
) -> Optional[Dict[str, Any]]:
    """Return the run immediately before `run_date`, or None if none exists."""
    runs = list_runs(runs_dir)
    earlier = [r for r in runs if r < run_date]
    if not earlier:
        return None
    return load_run(earlier[-1], runs_dir=runs_dir)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_create(args: argparse.Namespace) -> int:
    target = create_run_archive(
        run_date=args.run_date,
        runs_dir=args.runs_dir,
        path_2025=args.path_2025,
        path_2023=args.path_2023,
        how=args.how,
        notes=args.notes,
        overwrite=args.overwrite,
        update_latest=not args.no_update_latest,
        preflight=args.preflight,
    )
    print(f"Created run archive: {target}")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    runs = list_runs(args.runs_dir)
    if not runs:
        print(f"(no runs found under {args.runs_dir})")
        return 0
    latest = _latest_date_from_manifest(args.runs_dir)
    for r in runs:
        marker = "  <- latest" if r == latest else ""
        print(f"{r}{marker}")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    run = load_latest_run(args.runs_dir) if args.latest else load_run(
        args.run_date, runs_dir=args.runs_dir
    )
    summary = {
        "run_date": run["run_date"],
        "path": run["path"],
        "metadata": run["metadata"],
        "validation": run["validation"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Manage dated scoring-run archives (create / list / show)."
    )
    parser.add_argument(
        "--runs-dir", default=DEFAULT_RUNS_DIR,
        help="Directory that holds per-run folders (default: streamlit/runs).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Create a new dated run archive.")
    p_create.add_argument("--run-date", default=None,
                          help="YYYY-MM-DD (default: today in local time).")
    p_create.add_argument("--path-2025", default=DEFAULT_2025_PATH)
    p_create.add_argument("--path-2023", default=DEFAULT_2023_PATH)
    p_create.add_argument("--how", default="inner",
                          choices=["inner", "outer", "left", "right"])
    p_create.add_argument("--notes", default=None,
                          help="Free-form note stored in run_metadata.json.")
    p_create.add_argument("--overwrite", action="store_true",
                          help="Replace an existing run folder for the same date.")
    p_create.add_argument("--no-update-latest", action="store_true",
                          help="Do not update runs/latest.json.")
    p_create.add_argument(
        "--preflight", default="off",
        choices=["off", "warn", "strict"],
        help="Validate raw YCharts exports before archiving. "
             "'strict' aborts on any error finding.",
    )
    p_create.set_defaults(func=_cmd_create)

    p_list = sub.add_parser("list", help="List available run dates.")
    p_list.set_defaults(func=_cmd_list)

    p_show = sub.add_parser("show", help="Print run metadata + validation.")
    grp = p_show.add_mutually_exclusive_group(required=True)
    grp.add_argument("--run-date", help="YYYY-MM-DD of a specific run.")
    grp.add_argument("--latest", action="store_true",
                     help="Show the most recent run.")
    p_show.set_defaults(func=_cmd_show)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    _cli()
