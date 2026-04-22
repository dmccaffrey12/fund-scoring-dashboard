"""
Run Comparison
==============
Month-over-month comparison between two archived scoring runs.

Replaces the old "What Changed" view, which compared the 2023 system against
the 2025 system within a single snapshot. That is a cross-system diff, not
a true time diff. This module compares two dated run archives (from
`run_archive.py`) by Symbol and emits a bundle of change tables plus a
JSON summary.

Layout (by default, anchored to the newer run):

    runs/YYYY-MM-DD/comparison/prior_YYYY-MM-DD/
        score_movers.csv
        band_changes.csv
        quadrant_changes.csv
        action_flag_changes.csv
        new_funds.csv
        removed_funds.csv
        summary.json

Callable from Streamlit, Quarto, and Excel exports. The UI wiring is
deliberately left to a follow-up PR.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from run_archive import (
    DEFAULT_RUNS_DIR,
    list_runs,
    load_latest_run,
    load_prior_run,
    load_run,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCORE_COLUMNS: Tuple[str, ...] = (
    "Score_2023_Final",
    "Score_2025_Final",
    "Consensus_Rank",
)
BAND_COLUMNS: Tuple[str, ...] = ("Score_Band_2023", "Score_Band_2025")
QUADRANT_COLUMN = "Quadrant"
ACTION_FLAG_COLUMN = "Action_Flag"

# Carry-through columns on per-symbol detail rows.
METADATA_COLUMNS: Tuple[str, ...] = ("Name", "Category", "Fund_Type")

SCORE_MOVERS_NAME = "score_movers.csv"
BAND_CHANGES_NAME = "band_changes.csv"
QUADRANT_CHANGES_NAME = "quadrant_changes.csv"
ACTION_FLAG_CHANGES_NAME = "action_flag_changes.csv"
NEW_FUNDS_NAME = "new_funds.csv"
REMOVED_FUNDS_NAME = "removed_funds.csv"
SUMMARY_NAME = "summary.json"


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ComparisonResult:
    """In-memory bundle of the comparison outputs."""
    latest_date: str
    prior_date: str
    score_movers: pd.DataFrame
    band_changes: pd.DataFrame
    quadrant_changes: pd.DataFrame
    action_flag_changes: pd.DataFrame
    new_funds: pd.DataFrame
    removed_funds: pd.DataFrame
    summary: Dict[str, Any] = field(default_factory=dict)

    def tables(self) -> Dict[str, pd.DataFrame]:
        return {
            SCORE_MOVERS_NAME: self.score_movers,
            BAND_CHANGES_NAME: self.band_changes,
            QUADRANT_CHANGES_NAME: self.quadrant_changes,
            ACTION_FLAG_CHANGES_NAME: self.action_flag_changes,
            NEW_FUNDS_NAME: self.new_funds,
            REMOVED_FUNDS_NAME: self.removed_funds,
        }


class InsufficientRunsError(RuntimeError):
    """Raised when fewer than two runs are available to compare."""


# ---------------------------------------------------------------------------
# Core comparison
# ---------------------------------------------------------------------------

def _align(
    latest: pd.DataFrame,
    prior: pd.DataFrame,
) -> pd.DataFrame:
    """Merge two dual-score tables on Symbol with `_latest` / `_prior` suffixes."""
    if "Symbol" not in latest.columns or "Symbol" not in prior.columns:
        raise ValueError("Both tables must contain a 'Symbol' column.")

    merged = latest.merge(
        prior,
        on="Symbol",
        how="outer",
        suffixes=("_latest", "_prior"),
        indicator=True,
    )
    return merged


def _metadata_from_merged(merged: pd.DataFrame) -> pd.DataFrame:
    """Prefer the latest snapshot's metadata; fall back to prior."""
    out = pd.DataFrame({"Symbol": merged["Symbol"]})
    for col in METADATA_COLUMNS:
        latest_col = f"{col}_latest"
        prior_col = f"{col}_prior"
        if latest_col in merged.columns and prior_col in merged.columns:
            out[col] = merged[latest_col].fillna(merged[prior_col])
        elif latest_col in merged.columns:
            out[col] = merged[latest_col]
        elif prior_col in merged.columns:
            out[col] = merged[prior_col]
    return out


def _score_movers(
    merged: pd.DataFrame,
    metadata: pd.DataFrame,
    top_n: Optional[int] = None,
) -> pd.DataFrame:
    """Largest absolute changes for each numeric score/rank column.

    Returns a long-format frame keyed by (Symbol, Metric) so consumers
    (Quarto, Excel, Streamlit) can pivot however they like. Only funds
    present in both runs contribute — single-sided funds are captured in
    new_funds / removed_funds.
    """
    both = merged[merged["_merge"] == "both"].copy()
    records: List[Dict[str, Any]] = []

    for metric in SCORE_COLUMNS:
        latest_col = f"{metric}_latest"
        prior_col = f"{metric}_prior"
        if latest_col not in both.columns or prior_col not in both.columns:
            continue
        latest_val = pd.to_numeric(both[latest_col], errors="coerce")
        prior_val = pd.to_numeric(both[prior_col], errors="coerce")
        delta = latest_val - prior_val
        mask = delta.notna() & (delta != 0)
        if not mask.any():
            continue
        sub = both.loc[mask].copy()
        sub["Metric"] = metric
        sub["Value_Prior"] = prior_val[mask].values
        sub["Value_Latest"] = latest_val[mask].values
        sub["Delta"] = delta[mask].values
        sub["Abs_Delta"] = sub["Delta"].abs()
        keep = ["Symbol", "Metric", "Value_Prior", "Value_Latest", "Delta", "Abs_Delta"]
        records.append(sub[keep])

    if not records:
        return pd.DataFrame(
            columns=["Symbol", "Metric", "Value_Prior", "Value_Latest",
                     "Delta", "Abs_Delta", *METADATA_COLUMNS]
        )

    movers = pd.concat(records, ignore_index=True)
    movers = movers.merge(metadata, on="Symbol", how="left")
    movers = movers.sort_values(
        ["Metric", "Abs_Delta", "Symbol"],
        ascending=[True, False, True],
        kind="stable",
    ).reset_index(drop=True)

    if top_n is not None and top_n > 0:
        movers = (
            movers.sort_values(
                ["Metric", "Abs_Delta", "Symbol"],
                ascending=[True, False, True],
                kind="stable",
            )
            .groupby("Metric", as_index=False)
            .head(top_n)
            .reset_index(drop=True)
        )
    return movers


def _transition_table(
    merged: pd.DataFrame,
    metadata: pd.DataFrame,
    columns: Tuple[str, ...],
) -> pd.DataFrame:
    """Emit Symbol-level transitions for the given categorical columns.

    One row per (Symbol, Column) where the value changed between runs.
    """
    both = merged[merged["_merge"] == "both"].copy()
    records: List[Dict[str, Any]] = []

    for col in columns:
        latest_col = f"{col}_latest"
        prior_col = f"{col}_prior"
        if latest_col not in both.columns or prior_col not in both.columns:
            continue
        latest_val = both[latest_col]
        prior_val = both[prior_col]
        # Treat NaN-to-NaN as unchanged, anything else (NaN <-> value, value <-> value) as change if not equal.
        same = (latest_val == prior_val) | (latest_val.isna() & prior_val.isna())
        changed = ~same
        if not changed.any():
            continue
        sub = both.loc[changed].copy()
        sub["Column"] = col
        sub["From"] = prior_val[changed].values
        sub["To"] = latest_val[changed].values
        records.append(sub[["Symbol", "Column", "From", "To"]])

    if not records:
        return pd.DataFrame(columns=["Symbol", "Column", "From", "To", *METADATA_COLUMNS])

    trans = pd.concat(records, ignore_index=True)
    trans = trans.merge(metadata, on="Symbol", how="left")
    return trans.sort_values(
        ["Column", "Symbol"], kind="stable",
    ).reset_index(drop=True)


def _single_sided(
    merged: pd.DataFrame,
    side: str,
) -> pd.DataFrame:
    """Funds present only in one run. `side` is 'left_only' (new in latest)
    or 'right_only' (dropped from prior)."""
    if side not in {"left_only", "right_only"}:
        raise ValueError("side must be 'left_only' or 'right_only'")
    sub = merged[merged["_merge"] == side].copy()
    if sub.empty:
        return pd.DataFrame(
            columns=["Symbol", *METADATA_COLUMNS,
                     "Score_2023_Final", "Score_2025_Final",
                     "Score_Band_2023", "Score_Band_2025",
                     "Quadrant", "Action_Flag"]
        )
    suffix = "_latest" if side == "left_only" else "_prior"

    out = pd.DataFrame({"Symbol": sub["Symbol"].values})
    for col in METADATA_COLUMNS + (
        "Score_2023_Final", "Score_2025_Final",
        "Score_Band_2023", "Score_Band_2025",
        QUADRANT_COLUMN, ACTION_FLAG_COLUMN,
    ):
        src = f"{col}{suffix}"
        if src in sub.columns:
            out[col] = sub[src].values
    return out.sort_values("Symbol", kind="stable").reset_index(drop=True)


def _summary(
    result_kwargs: Dict[str, pd.DataFrame],
    latest_date: str,
    prior_date: str,
    latest_n: int,
    prior_n: int,
) -> Dict[str, Any]:
    movers = result_kwargs["score_movers"]
    band = result_kwargs["band_changes"]
    quad = result_kwargs["quadrant_changes"]
    action = result_kwargs["action_flag_changes"]
    new_f = result_kwargs["new_funds"]
    gone = result_kwargs["removed_funds"]

    return {
        "latest_run_date": latest_date,
        "prior_run_date": prior_date,
        "latest_row_count": int(latest_n),
        "prior_row_count": int(prior_n),
        "new_fund_count": int(len(new_f)),
        "removed_fund_count": int(len(gone)),
        "score_mover_count_by_metric": {
            str(m): int(len(g)) for m, g in movers.groupby("Metric")
        } if not movers.empty else {},
        "band_change_count_by_column": {
            str(c): int(len(g)) for c, g in band.groupby("Column")
        } if not band.empty else {},
        "quadrant_change_count": int(len(quad)),
        "action_flag_change_count": int(len(action)),
    }


def compare_runs(
    latest: Dict[str, Any],
    prior: Dict[str, Any],
    top_n_movers: Optional[int] = None,
) -> ComparisonResult:
    """Compare two archived runs (as returned by `load_run`).

    Parameters
    ----------
    latest, prior : dicts with keys {"run_date", "table"} (extras ignored).
    top_n_movers  : optional cap on mover rows per metric (largest |delta|).
    """
    if not isinstance(latest, dict) or not isinstance(prior, dict):
        raise TypeError("latest and prior must be run dicts (see run_archive.load_run).")
    if "table" not in latest or "table" not in prior:
        raise ValueError("run dicts must contain a 'table' DataFrame.")

    latest_date = latest.get("run_date", "unknown")
    prior_date = prior.get("run_date", "unknown")

    merged = _align(latest["table"], prior["table"])
    metadata = _metadata_from_merged(merged)

    score_movers = _score_movers(merged, metadata, top_n=top_n_movers)
    band_changes = _transition_table(merged, metadata, BAND_COLUMNS)
    quadrant_changes = _transition_table(merged, metadata, (QUADRANT_COLUMN,))
    action_flag_changes = _transition_table(merged, metadata, (ACTION_FLAG_COLUMN,))
    new_funds = _single_sided(merged, "left_only")
    removed_funds = _single_sided(merged, "right_only")

    summary = _summary(
        {
            "score_movers": score_movers,
            "band_changes": band_changes,
            "quadrant_changes": quadrant_changes,
            "action_flag_changes": action_flag_changes,
            "new_funds": new_funds,
            "removed_funds": removed_funds,
        },
        latest_date=latest_date,
        prior_date=prior_date,
        latest_n=len(latest["table"]),
        prior_n=len(prior["table"]),
    )

    return ComparisonResult(
        latest_date=latest_date,
        prior_date=prior_date,
        score_movers=score_movers,
        band_changes=band_changes,
        quadrant_changes=quadrant_changes,
        action_flag_changes=action_flag_changes,
        new_funds=new_funds,
        removed_funds=removed_funds,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Writing output
# ---------------------------------------------------------------------------

def default_comparison_dir(
    runs_dir: str,
    latest_date: str,
    prior_date: str,
) -> str:
    """Canonical output directory under the latest run."""
    return os.path.join(
        runs_dir, latest_date, "comparison", f"prior_{prior_date}"
    )


def write_comparison(
    result: ComparisonResult,
    out_dir: str,
) -> Dict[str, str]:
    """Persist a ComparisonResult to CSVs + summary.json. Returns file paths."""
    os.makedirs(out_dir, exist_ok=True)
    paths: Dict[str, str] = {}
    for fname, df in result.tables().items():
        path = os.path.join(out_dir, fname)
        df.to_csv(path, index=False)
        paths[fname] = path
    summary_path = os.path.join(out_dir, SUMMARY_NAME)
    with open(summary_path, "w") as f:
        json.dump(result.summary, f, indent=2, sort_keys=True)
    paths[SUMMARY_NAME] = summary_path
    return paths


# ---------------------------------------------------------------------------
# High-level orchestration
# ---------------------------------------------------------------------------

def resolve_runs(
    runs_dir: str = DEFAULT_RUNS_DIR,
    latest_date: Optional[str] = None,
    prior_date: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Pick two runs from disk based on optional explicit dates.

    Defaults:
      - `latest_date` → load_latest_run()
      - `prior_date`  → run immediately before the resolved latest.

    Raises InsufficientRunsError when fewer than two usable runs exist.
    """
    runs = list_runs(runs_dir)
    if len(runs) < 2 and (latest_date is None or prior_date is None):
        raise InsufficientRunsError(
            f"Need at least two runs under {runs_dir} to compare; found {len(runs)}. "
            "Pass explicit --latest-date and --prior-date to override."
        )

    latest = load_run(latest_date, runs_dir=runs_dir) if latest_date else load_latest_run(runs_dir)
    if prior_date is None:
        prior = load_prior_run(latest["run_date"], runs_dir=runs_dir)
        if prior is None:
            raise InsufficientRunsError(
                f"No run earlier than {latest['run_date']} found under {runs_dir}."
            )
    else:
        prior = load_run(prior_date, runs_dir=runs_dir)

    if latest["run_date"] == prior["run_date"]:
        raise ValueError(
            f"Latest and prior run dates are identical ({latest['run_date']}); "
            "pick two distinct runs."
        )
    return latest, prior


def run_comparison(
    runs_dir: str = DEFAULT_RUNS_DIR,
    latest_date: Optional[str] = None,
    prior_date: Optional[str] = None,
    out_dir: Optional[str] = None,
    top_n_movers: Optional[int] = None,
    write: bool = True,
) -> Tuple[ComparisonResult, Optional[Dict[str, str]]]:
    """End-to-end: resolve runs, compute comparison, optionally persist.

    Returns (ComparisonResult, paths_dict | None).
    """
    latest, prior = resolve_runs(runs_dir, latest_date, prior_date)
    result = compare_runs(latest, prior, top_n_movers=top_n_movers)
    paths: Optional[Dict[str, str]] = None
    if write:
        target = out_dir or default_comparison_dir(
            runs_dir, result.latest_date, result.prior_date
        )
        paths = write_comparison(result, target)
    return result, paths


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_compare(args: argparse.Namespace) -> int:
    try:
        result, paths = run_comparison(
            runs_dir=args.runs_dir,
            latest_date=args.latest_date,
            prior_date=args.prior_date,
            out_dir=args.out_dir,
            top_n_movers=args.top_n,
            write=not args.dry_run,
        )
    except InsufficientRunsError as e:
        print(f"error: {e}")
        return 2
    except FileNotFoundError as e:
        print(f"error: {e}")
        return 2

    print(json.dumps(result.summary, indent=2, sort_keys=True))
    if paths:
        print("\nWrote:")
        for name, p in sorted(paths.items()):
            print(f"  {name}: {p}")
    return 0


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Compare two archived scoring runs and emit change tables."
    )
    parser.add_argument(
        "--runs-dir", default=DEFAULT_RUNS_DIR,
        help="Directory that holds per-run folders (default: streamlit/runs).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "compare",
        help="Run a comparison. Defaults to latest vs prior.",
    )
    p.add_argument("--latest-date", default=None,
                   help="YYYY-MM-DD of the newer run (default: latest archived).")
    p.add_argument("--prior-date", default=None,
                   help="YYYY-MM-DD of the older run (default: the run immediately before --latest-date).")
    p.add_argument("--out-dir", default=None,
                   help="Explicit output directory. Default: <runs-dir>/<latest>/comparison/prior_<prior>/.")
    p.add_argument("--top-n", type=int, default=None,
                   help="Cap mover rows per metric (largest |delta| first).")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute but do not write CSV/JSON output.")
    p.set_defaults(func=_cmd_compare)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    _cli()
