"""
YCharts Intake Validator
========================
Preflight checks for raw YCharts CSV exports that feed the scoring engine.

Two schemas are supported:
    - `2025` — the 29-column "2025 Scoring System" export
    - `2023` — the 28-column "2023 Scoring System" legacy export

Usage (library):

    from ycharts_intake import validate_file, validate_pair

    report = validate_file("path/to/2025.csv", schema="2025")
    if report["failed"]:
        raise SystemExit(summarize(report))

    pair = validate_pair("path/to/2025.csv", "path/to/2023.csv")
    print(summarize(pair))

Usage (CLI):

    python ycharts_intake.py --path-2025 path/to/2025.csv
    python ycharts_intake.py --path-2023 path/to/2023.csv
    python ycharts_intake.py --path-2025 a.csv --path-2023 b.csv \
        --json-out report.json

Severity levels:
    error   — blocks downstream scoring (missing required column, unparseable
              critical field, etc). Sets `failed = True`.
    warning — parseable but suspicious (duplicate symbols, high null rate,
              weak joinability).
    info    — descriptive only (row count, null-rate summary per column).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

REQUIRED_2025: List[str] = [
    "Symbol",
    "Name",
    "Index Fund",
    "Category Name",
    "Net Expense Ratio",
    "R-Squared (vs Category) (5Y)",
    "Share Class Assets Under Management",
    "Max Drawdown (5Y)",
    "Max Drawdown (10Y)",
    "Information Ratio (vs Category) (3Y)",
    "Historical Sortino (3Y)",
    "Upside (vs Category) (5Y)",
    "Downside (vs Category) (5Y)",
    "3 Year Total Returns (Daily)",
    "5 Year Total Returns (Daily)",
    "10 Year Total Returns (Daily)",
]

# Critical numeric columns for 2025 — unparseable values here are errors.
CRITICAL_NUMERIC_2025: List[str] = [
    "Net Expense Ratio",
    "Share Class Assets Under Management",
]

# Non-critical numeric columns for 2025 — unparseable values are warnings.
NUMERIC_2025: List[str] = [
    "Tracking Error (vs Category) (3Y)",
    "Tracking Error (vs Category) (5Y)",
    "Tracking Error (vs Category) (10Y)",
    "R-Squared (vs Category) (5Y)",
    "Downside (vs Category) (5Y)",
    "Downside (vs Category) (10Y)",
    "Max Drawdown (5Y)",
    "Max Drawdown (10Y)",
    "Information Ratio (vs Category) (3Y)",
    "Information Ratio (vs Category) (5Y)",
    "Information Ratio (vs Category) (10Y)",
    "Historical Sortino (3Y)",
    "Historical Sortino (5Y)",
    "Historical Sortino (10Y)",
    "Upside (vs Category) (3Y)",
    "Upside (vs Category) (5Y)",
    "Upside (vs Category) (10Y)",
    "3 Year Total Returns (Daily)",
    "5 Year Total Returns (Daily)",
    "10 Year Total Returns (Daily)",
    "2025 Scoring System",
]

REQUIRED_2023: List[str] = [
    "Symbol",
    "Name",
    "Category Name",
    "R-Squared (vs Category) (5Y)",
    "Max Drawdown (5Y)",
    "Max Drawdown (10Y)",
    "Share Class Assets Under Management",
    "Annual Report Expense Ratio",
]

CRITICAL_NUMERIC_2023: List[str] = [
    "Annual Report Expense Ratio",
    "Share Class Assets Under Management",
]

NUMERIC_2023: List[str] = [
    "3 Year Total NAV Returns Category Rank",
    "5 Year Total NAV Returns Category Rank",
    "10 Year Total NAV Returns Category Rank",
    "Annualized 5 Year Total Returns (Monthly)",
    "Alpha (vs Category) (5Y)",
    "Beta (vs Category) (5Y)",
    "R-Squared (vs Category) (5Y)",
    "Max Drawdown (5Y)",
    "Upside (5Y)",
    "Downside (5Y)",
    "Upside/Downside Ratio (5Y)",
    "Annualized 10 Year Total Returns (Monthly)",
    "Alpha (vs Category) (10Y)",
    "Beta (vs Category) (10Y)",
    "R-Squared (vs Category) (10Y)",
    "Max Drawdown (10Y)",
    "Upside (10Y)",
    "Downside (10Y)",
    "Upside/Downside Ratio (10Y)",
    "Median Manager Tenure",
    "Average Manager Tenure",
    "Total Assets Under Management",
]

# Truthy / falsy tokens accepted by YCharts "Index Fund" column. Anything else
# (other than blank) is reported as unparseable.
INDEX_FUND_TRUE: set = {"true", "t", "yes", "y", "1", "1.0"}
INDEX_FUND_FALSE: set = {"false", "f", "no", "n", "0", "0.0"}

# Default warning threshold for null rate per critical numeric column.
DEFAULT_NULL_RATE_WARN = 0.50

SCHEMAS: Dict[str, Dict[str, Any]] = {
    "2025": {
        "required": REQUIRED_2025,
        "critical_numeric": CRITICAL_NUMERIC_2025,
        "numeric": NUMERIC_2025,
        "needs_index_fund": True,
    },
    "2023": {
        "required": REQUIRED_2023,
        "critical_numeric": CRITICAL_NUMERIC_2023,
        "numeric": NUMERIC_2023,
        "needs_index_fund": False,
    },
}


# ---------------------------------------------------------------------------
# Finding messages
# ---------------------------------------------------------------------------

def _finding(severity: str, code: str, message: str, **extra: Any) -> Dict[str, Any]:
    out = {"severity": severity, "code": code, "message": message}
    if extra:
        out["details"] = extra
    return out


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_required_columns(
    df: pd.DataFrame, required: Iterable[str]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    missing = [c for c in required if c not in df.columns]
    findings: List[Dict[str, Any]] = []
    if missing:
        findings.append(_finding(
            "error", "missing_required_columns",
            f"Required columns missing: {missing}",
            missing=missing,
        ))
    return findings, missing


def _check_symbols(df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {"blank_symbol_count": 0, "duplicate_symbol_count": 0,
                             "duplicate_symbols": []}
    if "Symbol" not in df.columns:
        return findings, stats

    symbol = df["Symbol"]
    # Blank / null symbols — always an error.
    blank_mask = symbol.isna() | (symbol.astype(str).str.strip() == "")
    blank_count = int(blank_mask.sum())
    stats["blank_symbol_count"] = blank_count
    if blank_count:
        findings.append(_finding(
            "error", "blank_symbols",
            f"{blank_count} row(s) have a blank or null Symbol",
            count=blank_count,
        ))

    non_blank = symbol[~blank_mask].astype(str).str.strip()
    dup_mask = non_blank.duplicated(keep=False)
    dup_values = sorted(set(non_blank[dup_mask]))
    stats["duplicate_symbol_count"] = int(dup_mask.sum())
    stats["duplicate_symbols"] = dup_values[:50]
    if dup_values:
        findings.append(_finding(
            "warning", "duplicate_symbols",
            f"{len(dup_values)} symbol(s) appear more than once "
            f"(total duplicate rows: {int(dup_mask.sum())})",
            distinct_duplicate_count=len(dup_values),
            duplicate_rows=int(dup_mask.sum()),
            sample=dup_values[:10],
        ))
    return findings, stats


def _check_numeric_parseability(
    df: pd.DataFrame,
    columns: Iterable[str],
    severity: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, int]]]:
    """
    Check which non-null values in each column fail numeric coercion.
    Returns a list of findings and a per-column summary.
    """
    findings: List[Dict[str, Any]] = []
    summary: Dict[str, Dict[str, int]] = {}
    for col in columns:
        if col not in df.columns:
            continue
        series = df[col]
        # Treat empty strings as null before coercion so they don't
        # get counted as "unparseable".
        cleaned = series.replace(r"^\s*$", pd.NA, regex=True)
        coerced = pd.to_numeric(cleaned, errors="coerce")
        # Values that were non-null originally but became NaN are unparseable.
        original_non_null = cleaned.notna()
        now_null = coerced.isna()
        bad_mask = original_non_null & now_null
        bad_count = int(bad_mask.sum())
        total = int(len(series))
        null_count = int(series.isna().sum() + (series.astype(str).str.strip() == "").sum()
                          - series.isna().sum())  # blanks that weren't already NaN
        null_count = int((~original_non_null).sum())
        summary[col] = {
            "rows": total,
            "null_count": null_count,
            "unparseable_count": bad_count,
        }
        if bad_count:
            samples = series[bad_mask].astype(str).head(5).tolist()
            findings.append(_finding(
                severity, "unparseable_numeric",
                f"Column {col!r}: {bad_count} non-null value(s) could not be "
                f"coerced to numeric",
                column=col, count=bad_count, samples=samples,
            ))
    return findings, summary


def _check_index_fund(df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {"passive_count": 0, "active_count": 0,
                             "unparseable_count": 0}
    if "Index Fund" not in df.columns:
        return findings, stats

    series = df["Index Fund"]
    if series.dtype == bool:
        stats["passive_count"] = int(series.sum())
        stats["active_count"] = int((~series).sum())
        return findings, stats

    normalized = series.astype(str).str.strip().str.lower()
    is_null = series.isna() | (normalized == "") | (normalized == "nan")
    is_true = normalized.isin(INDEX_FUND_TRUE) & ~is_null
    is_false = normalized.isin(INDEX_FUND_FALSE) & ~is_null
    bad_mask = ~(is_true | is_false | is_null)
    bad_count = int(bad_mask.sum())
    null_count = int(is_null.sum())

    stats["passive_count"] = int(is_true.sum())
    stats["active_count"] = int(is_false.sum())
    stats["unparseable_count"] = bad_count
    stats["null_count"] = null_count

    if bad_count:
        samples = series[bad_mask].astype(str).head(5).tolist()
        findings.append(_finding(
            "error", "unparseable_index_fund",
            f"Column 'Index Fund' has {bad_count} value(s) that do not parse "
            f"as True/False",
            count=bad_count, samples=samples,
        ))
    if null_count:
        findings.append(_finding(
            "warning", "null_index_fund",
            f"Column 'Index Fund' has {null_count} null/blank value(s); "
            f"these funds cannot be classified as Passive or Active",
            count=null_count,
        ))
    return findings, stats


def _null_rate_summary(
    df: pd.DataFrame,
    columns: Iterable[str],
) -> Dict[str, float]:
    out: Dict[str, float] = {}
    n = len(df)
    if n == 0:
        return out
    for col in columns:
        if col not in df.columns:
            continue
        series = df[col]
        cleaned = series.replace(r"^\s*$", pd.NA, regex=True)
        null_count = int(cleaned.isna().sum())
        out[col] = round(null_count / n, 4)
    return out


def _check_null_rate(
    null_rates: Dict[str, float],
    critical: Iterable[str],
    threshold: float,
) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for col in critical:
        rate = null_rates.get(col)
        if rate is None:
            continue
        if rate >= threshold:
            findings.append(_finding(
                "warning", "high_null_rate",
                f"Critical column {col!r} is {rate * 100:.1f}% null "
                f"(threshold {threshold * 100:.0f}%)",
                column=col, null_rate=rate, threshold=threshold,
            ))
    return findings


# ---------------------------------------------------------------------------
# Public: validate a single file
# ---------------------------------------------------------------------------

def validate_dataframe(
    df: pd.DataFrame,
    schema: str,
    *,
    null_rate_threshold: float = DEFAULT_NULL_RATE_WARN,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate an in-memory DataFrame against the named YCharts schema."""
    if schema not in SCHEMAS:
        raise ValueError(f"Unknown schema {schema!r}; expected one of "
                         f"{sorted(SCHEMAS)}")
    spec = SCHEMAS[schema]
    required: List[str] = spec["required"]
    critical_numeric: List[str] = spec["critical_numeric"]
    numeric_cols: List[str] = spec["numeric"]

    findings: List[Dict[str, Any]] = []

    col_findings, missing = _check_required_columns(df, required)
    findings.extend(col_findings)

    # Only continue numeric / symbol checks against columns that actually exist.
    sym_findings, symbol_stats = _check_symbols(df)
    findings.extend(sym_findings)

    crit_findings, crit_summary = _check_numeric_parseability(
        df, critical_numeric, severity="error",
    )
    findings.extend(crit_findings)

    num_findings, num_summary = _check_numeric_parseability(
        df, numeric_cols, severity="warning",
    )
    findings.extend(num_findings)

    idx_findings, idx_stats = ({}, {})
    if spec["needs_index_fund"]:
        idx_findings, idx_stats = _check_index_fund(df)
        findings.extend(idx_findings)

    all_numeric = list(dict.fromkeys(list(critical_numeric) + list(numeric_cols)))
    null_rates = _null_rate_summary(df, all_numeric)
    findings.extend(_check_null_rate(null_rates, critical_numeric,
                                     null_rate_threshold))

    findings.append(_finding(
        "info", "row_count",
        f"Row count: {len(df)}",
        count=int(len(df)),
    ))

    failed = any(f["severity"] == "error" for f in findings)
    counts = {
        "error": sum(1 for f in findings if f["severity"] == "error"),
        "warning": sum(1 for f in findings if f["severity"] == "warning"),
        "info": sum(1 for f in findings if f["severity"] == "info"),
    }

    return {
        "source": source,
        "schema": schema,
        "row_count": int(len(df)),
        "column_count": int(df.shape[1]),
        "columns": list(df.columns),
        "required_columns": list(required),
        "missing_required_columns": missing,
        "symbol_stats": symbol_stats,
        "index_fund_stats": idx_stats if spec["needs_index_fund"] else None,
        "numeric_summary": {**crit_summary, **num_summary},
        "null_rates": null_rates,
        "findings": findings,
        "finding_counts": counts,
        "failed": failed,
    }


def _read_csv(path: str) -> pd.DataFrame:
    # dtype=str keeps YCharts' mixed-type columns intact for parseability checks.
    # We still let pandas infer types in numeric_summary via pd.to_numeric.
    return pd.read_csv(path, dtype=str, keep_default_na=True)


def validate_file(
    path: str,
    schema: str,
    *,
    null_rate_threshold: float = DEFAULT_NULL_RATE_WARN,
) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {
            "source": path,
            "schema": schema,
            "failed": True,
            "finding_counts": {"error": 1, "warning": 0, "info": 0},
            "findings": [_finding("error", "file_not_found",
                                  f"File does not exist: {path}")],
        }
    try:
        df = _read_csv(path)
    except Exception as exc:  # pragma: no cover - pandas error passthrough
        return {
            "source": path,
            "schema": schema,
            "failed": True,
            "finding_counts": {"error": 1, "warning": 0, "info": 0},
            "findings": [_finding("error", "csv_read_error",
                                  f"Could not read CSV: {exc}")],
        }
    return validate_dataframe(
        df, schema,
        null_rate_threshold=null_rate_threshold,
        source=path,
    )


# ---------------------------------------------------------------------------
# Public: validate both 2025 + 2023 and check joinability
# ---------------------------------------------------------------------------

def _joinability(
    df_2025: Optional[pd.DataFrame],
    df_2023: Optional[pd.DataFrame],
) -> Dict[str, Any]:
    if df_2025 is None or df_2023 is None:
        return {"available": False}
    if "Symbol" not in df_2025.columns or "Symbol" not in df_2023.columns:
        return {"available": False, "reason": "Symbol column missing from one side"}
    sym_2025 = set(df_2025["Symbol"].dropna().astype(str).str.strip()) - {""}
    sym_2023 = set(df_2023["Symbol"].dropna().astype(str).str.strip()) - {""}
    common = sym_2025 & sym_2023
    only_2025 = sym_2025 - sym_2023
    only_2023 = sym_2023 - sym_2025
    smaller = max(1, min(len(sym_2025), len(sym_2023)))
    overlap_rate = round(len(common) / smaller, 4)
    return {
        "available": True,
        "symbols_2025": len(sym_2025),
        "symbols_2023": len(sym_2023),
        "symbols_common": len(common),
        "symbols_only_2025": len(only_2025),
        "symbols_only_2023": len(only_2023),
        "overlap_rate_vs_smaller": overlap_rate,
        "sample_only_2025": sorted(only_2025)[:10],
        "sample_only_2023": sorted(only_2023)[:10],
    }


def validate_pair(
    path_2025: Optional[str] = None,
    path_2023: Optional[str] = None,
    *,
    null_rate_threshold: float = DEFAULT_NULL_RATE_WARN,
    min_overlap_rate: float = 0.80,
) -> Dict[str, Any]:
    """Validate one or both files and, if both are supplied, report joinability."""
    report_2025: Optional[Dict[str, Any]] = None
    report_2023: Optional[Dict[str, Any]] = None
    df_2025: Optional[pd.DataFrame] = None
    df_2023: Optional[pd.DataFrame] = None

    if path_2025:
        report_2025 = validate_file(
            path_2025, "2025", null_rate_threshold=null_rate_threshold,
        )
        if os.path.isfile(path_2025):
            try:
                df_2025 = _read_csv(path_2025)
            except Exception:
                df_2025 = None
    if path_2023:
        report_2023 = validate_file(
            path_2023, "2023", null_rate_threshold=null_rate_threshold,
        )
        if os.path.isfile(path_2023):
            try:
                df_2023 = _read_csv(path_2023)
            except Exception:
                df_2023 = None

    join = _joinability(df_2025, df_2023)
    join_findings: List[Dict[str, Any]] = []
    if join.get("available"):
        rate = join["overlap_rate_vs_smaller"]
        if rate < min_overlap_rate:
            join_findings.append(_finding(
                "warning", "low_symbol_overlap",
                f"Only {rate * 100:.1f}% of symbols overlap between the two "
                f"files (threshold {min_overlap_rate * 100:.0f}%)",
                overlap_rate=rate, threshold=min_overlap_rate,
            ))
        join_findings.append(_finding(
            "info", "join_summary",
            f"Common symbols: {join['symbols_common']} "
            f"(2025-only: {join['symbols_only_2025']}, "
            f"2023-only: {join['symbols_only_2023']})",
        ))

    # Roll up pair-level failure: any file-level failure OR any join error.
    pair_failed = bool(
        (report_2025 and report_2025.get("failed")) or
        (report_2023 and report_2023.get("failed")) or
        any(f["severity"] == "error" for f in join_findings)
    )
    pair_counts = {"error": 0, "warning": 0, "info": 0}
    for r in (report_2025, report_2023):
        if not r:
            continue
        for sev, count in r.get("finding_counts", {}).items():
            pair_counts[sev] = pair_counts.get(sev, 0) + count
    for f in join_findings:
        pair_counts[f["severity"]] = pair_counts.get(f["severity"], 0) + 1

    return {
        "report_2025": report_2025,
        "report_2023": report_2023,
        "join": join,
        "join_findings": join_findings,
        "failed": pair_failed,
        "finding_counts": pair_counts,
    }


# ---------------------------------------------------------------------------
# Human-readable summary
# ---------------------------------------------------------------------------

def _summarize_single(report: Dict[str, Any], label: str) -> List[str]:
    if report is None:
        return []
    lines = [f"=== {label} ({report.get('schema')}) ==="]
    lines.append(f"  source: {report.get('source')}")
    lines.append(f"  rows: {report.get('row_count')}  "
                 f"cols: {report.get('column_count')}")
    counts = report.get("finding_counts", {})
    lines.append(
        f"  findings: {counts.get('error', 0)} error, "
        f"{counts.get('warning', 0)} warning, {counts.get('info', 0)} info"
    )
    lines.append(f"  status: {'FAIL' if report.get('failed') else 'PASS'}")
    for f in report.get("findings", []):
        sev = f["severity"].upper().ljust(7)
        lines.append(f"    [{sev}] {f['code']}: {f['message']}")
    return lines


def summarize(report: Dict[str, Any]) -> str:
    """Render a human-readable summary of a single-file or pair report."""
    lines: List[str] = []
    if "report_2025" in report or "report_2023" in report:
        if report.get("report_2025"):
            lines.extend(_summarize_single(report["report_2025"], "2025 export"))
        if report.get("report_2023"):
            lines.extend(_summarize_single(report["report_2023"], "2023 export"))
        join = report.get("join") or {}
        if join.get("available"):
            lines.append("=== Joinability ===")
            lines.append(
                f"  common: {join['symbols_common']}  "
                f"2025-only: {join['symbols_only_2025']}  "
                f"2023-only: {join['symbols_only_2023']}  "
                f"overlap: {join['overlap_rate_vs_smaller'] * 100:.1f}%"
            )
        for f in report.get("join_findings", []):
            sev = f["severity"].upper().ljust(7)
            lines.append(f"    [{sev}] {f['code']}: {f['message']}")
        lines.append(
            f"=== PAIR STATUS: {'FAIL' if report.get('failed') else 'PASS'} ==="
        )
    else:
        lines.extend(_summarize_single(report, report.get("schema", "file")))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Run-archive integration helper
# ---------------------------------------------------------------------------

def preflight_for_archive(
    path_2025: str,
    path_2023: str,
    *,
    strict: bool = True,
    null_rate_threshold: float = DEFAULT_NULL_RATE_WARN,
) -> Dict[str, Any]:
    """
    Validate both raw exports before archive creation.

    When `strict=True` (the default), this raises ``ValueError`` if either
    file has any error-level finding. The returned dict is the full pair
    report regardless of outcome — callers can persist it alongside the
    run metadata.
    """
    pair = validate_pair(
        path_2025=path_2025,
        path_2023=path_2023,
        null_rate_threshold=null_rate_threshold,
    )
    if strict and pair["failed"]:
        raise ValueError(
            "YCharts intake validation failed:\n" + summarize(pair)
        )
    return pair


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate raw YCharts CSV exports (2023 and/or 2025).",
    )
    parser.add_argument("--path-2025", help="Path to a 2025-schema YCharts CSV.")
    parser.add_argument("--path-2023", help="Path to a 2023-schema YCharts CSV.")
    parser.add_argument(
        "--null-rate-threshold", type=float, default=DEFAULT_NULL_RATE_WARN,
        help="Warn when a critical numeric column has null rate ≥ this "
             "fraction (default 0.50).",
    )
    parser.add_argument(
        "--min-overlap-rate", type=float, default=0.80,
        help="Warn when symbol overlap between 2025 and 2023 is below this "
             "fraction of the smaller file (default 0.80).",
    )
    parser.add_argument(
        "--json-out", default=None,
        help="If set, write the full validation report to this path.",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Do not print the human-readable summary to stdout.",
    )
    args = parser.parse_args(argv)

    if not args.path_2025 and not args.path_2023:
        parser.error("Provide at least one of --path-2025 / --path-2023.")

    report = validate_pair(
        path_2025=args.path_2025,
        path_2023=args.path_2023,
        null_rate_threshold=args.null_rate_threshold,
        min_overlap_rate=args.min_overlap_rate,
    )

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(report, f, indent=2, sort_keys=True, default=str)

    if not args.quiet:
        print(summarize(report))

    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(_cli())
