"""
Model Holdings Intake Validator
===============================
Preflight checks for a "current model portfolios" CSV — the overlay input
that lets the committee see how actual model holdings stack up against the
scored fund universe.

Model holdings are an *overlay* on top of the scored universe; they are not
part of the dual-score methodology.

Required columns:
    Model_Name       — free-text model label (e.g. "Moderate Growth").
    Symbol           — ticker; join key against the dual-score table.
    Target_Weight    — numeric weight. Accepts percent or fraction notation.

Optional columns (preserved on the overlay output if supplied):
    Fund_Name, Sleeve, Status, Internal_Category, Notes.

Severity conventions match ``ycharts_intake``:
    error   — blocks overlay generation (missing required col, unparseable
              required field, duplicate Model+Symbol pair, ...).
    warning — parseable but suspicious (per-model total weight not close to
              100%, low coverage against dual-score table, ...).
    info    — descriptive counters.

Public API:
    validate_model_holdings_dataframe(df, *, dual_score_symbols=None)
    validate_model_holdings_file(path, *, dual_score_symbols=None)
    summarize(report) -> str
    normalize_weights(df) -> pd.DataFrame  # returns a copy with Target_Weight
                                           # coerced to fractional (0.0-1.0).
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set

import pandas as pd

from symbol_aliases import (
    apply_aliases,
    load_default_aliases,
    summarize_alias_usage,
)


REQUIRED_COLUMNS: List[str] = ["Model_Name", "Symbol", "Target_Weight"]
OPTIONAL_COLUMNS: List[str] = [
    "Fund_Name", "Sleeve", "Status", "Internal_Category", "Notes",
]

# Per-model target weights should roughly sum to 1.0 (fractional) once
# normalised. Anything outside this tolerance surfaces as a warning.
WEIGHT_SUM_TOLERANCE = 0.02

# Warn when fewer than this fraction of holdings match the scored fund
# universe (by Symbol).
DEFAULT_MIN_COVERAGE_WARN = 0.80


# ---------------------------------------------------------------------------
# Finding helpers
# ---------------------------------------------------------------------------

def _finding(severity: str, code: str, message: str, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if extra:
        out["details"] = extra
    return out


# ---------------------------------------------------------------------------
# Weight coercion
# ---------------------------------------------------------------------------

def _coerce_weight(value: Any) -> Optional[float]:
    """Parse a single weight cell into a Python float, or None if unparseable.

    Accepts percent strings ("25%", "  3.5 %"), fractional strings ("0.25"),
    integer strings ("25"), and raw numerics. Empty / NaN returns None.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return None
        return float(value)
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    had_percent = s.endswith("%")
    if had_percent:
        s = s[:-1].strip()
    try:
        num = float(s)
    except ValueError:
        return None
    if had_percent:
        num /= 100.0
    return num


def _looks_like_percent(series: pd.Series) -> bool:
    """Heuristic: are these weights expressed in percent (0-100) rather than
    fractional (0-1)?"""
    clean = series.dropna()
    if clean.empty:
        return False
    # If any value exceeds 1.5 (i.e. 150%), we're almost certainly in percent
    # land. Conversely if everything is below ~1.2 we treat as fractional.
    return float(clean.max()) > 1.5


def normalize_weights(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``df`` with Target_Weight coerced to fractional floats.

    Also adds a ``Target_Weight_Pct`` column (percent, 0-100) for convenience.
    """
    out = df.copy()
    if "Target_Weight" not in out.columns:
        return out
    parsed = out["Target_Weight"].apply(_coerce_weight)
    if _looks_like_percent(parsed):
        parsed = parsed / 100.0
    out["Target_Weight"] = parsed.astype(float)
    out["Target_Weight_Pct"] = (out["Target_Weight"] * 100.0).astype(float)
    return out


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_required_columns(df: pd.DataFrame) -> List[Dict[str, Any]]:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return [_finding(
            "error", "missing_required_columns",
            f"Required columns missing: {missing}",
            missing=missing,
        )]
    return []


def _check_symbols_present(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if "Symbol" not in df.columns:
        return []
    blank = df["Symbol"].isna() | (df["Symbol"].astype(str).str.strip() == "")
    count = int(blank.sum())
    if count:
        return [_finding(
            "error", "blank_symbols",
            f"{count} row(s) have a blank or null Symbol",
            count=count,
        )]
    return []


def _check_model_name_present(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if "Model_Name" not in df.columns:
        return []
    blank = df["Model_Name"].isna() | (df["Model_Name"].astype(str).str.strip() == "")
    count = int(blank.sum())
    if count:
        return [_finding(
            "error", "blank_model_names",
            f"{count} row(s) have a blank or null Model_Name",
            count=count,
        )]
    return []


def _check_weight_parseability(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if "Target_Weight" not in df.columns:
        return []
    raw = df["Target_Weight"]
    cleaned = raw.replace(r"^\s*$", pd.NA, regex=True)
    parsed = cleaned.apply(_coerce_weight)
    bad_mask = cleaned.notna() & parsed.isna()
    bad = int(bad_mask.sum())
    if bad:
        samples = raw[bad_mask].astype(str).head(5).tolist()
        return [_finding(
            "error", "unparseable_weight",
            f"{bad} Target_Weight value(s) could not be parsed as a number",
            count=bad, samples=samples,
        )]
    return []


def _check_duplicate_model_symbol(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if not {"Model_Name", "Symbol"}.issubset(df.columns):
        return []
    key = (
        df["Model_Name"].fillna("").astype(str) + "|"
        + df["Symbol"].fillna("").astype(str)
    )
    dup_mask = key.duplicated(keep=False)
    dup_count = int(dup_mask.sum())
    if not dup_count:
        return []
    samples = sorted(set(key[dup_mask]))[:10]
    return [_finding(
        "error", "duplicate_model_symbol",
        f"{dup_count} row(s) have a duplicate (Model_Name, Symbol) pair",
        count=dup_count, samples=samples,
    )]


def _check_weight_sums(
    df: pd.DataFrame,
    tolerance: float = WEIGHT_SUM_TOLERANCE,
) -> (List[Dict[str, Any]], Dict[str, float]):
    findings: List[Dict[str, Any]] = []
    sums: Dict[str, float] = {}
    if not {"Model_Name", "Target_Weight"}.issubset(df.columns):
        return findings, sums
    norm = normalize_weights(df)
    grouped = norm.groupby("Model_Name", dropna=False)["Target_Weight"].sum()
    for model, total in grouped.items():
        sums[str(model)] = float(total)
        if pd.isna(total):
            continue
        if abs(float(total) - 1.0) > tolerance:
            findings.append(_finding(
                "warning", "weight_sum_off",
                f"Model {model!r} target weights sum to {float(total) * 100:.2f}% "
                f"(expected ~100%, tolerance ±{tolerance * 100:.0f}%)",
                model=str(model), total=float(total), tolerance=tolerance,
            ))
    return findings, sums


def _check_coverage(
    df: pd.DataFrame,
    dual_score_symbols: Optional[Iterable[str]],
    threshold: float = DEFAULT_MIN_COVERAGE_WARN,
    alias_map: Optional[Mapping[str, str]] = None,
) -> (List[Dict[str, Any]], Dict[str, Any]):
    """Coverage check that applies symbol aliases before comparing vs. the universe.

    Reports alias-applied counts separately from still-unscored symbols so a
    share-class mismatch doesn't look like a coverage gap.
    """
    findings: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {"available": False}
    if dual_score_symbols is None or "Symbol" not in df.columns:
        return findings, stats
    universe: Set[str] = {
        str(s).strip().upper() for s in dual_score_symbols if str(s).strip()
    }
    raw_holdings = df["Symbol"].dropna().astype(str).str.strip()
    raw_holdings = raw_holdings[raw_holdings != ""]
    if raw_holdings.empty:
        return findings, stats

    resolved = apply_aliases(
        df.loc[raw_holdings.index, ["Symbol"]],
        alias_map=alias_map,
        universe=universe,
    )
    alias_summary = summarize_alias_usage(resolved, universe=universe)

    total = int(len(raw_holdings))
    scoring = resolved["Scoring_Symbol"].astype(str).str.upper()
    covered_mask = scoring.isin(universe)
    covered = int(covered_mask.sum())

    alias_applied_mask = resolved["Alias_Applied"].astype(bool)
    alias_applied_rows = int(alias_applied_mask.sum())
    alias_covered_rows = int((alias_applied_mask & covered_mask).sum())

    missing_mask = ~covered_mask
    missing_originals = sorted(
        set(resolved.loc[missing_mask, "Original_Symbol"].astype(str))
    )
    rate = round(covered / total, 4) if total else 0.0

    stats = {
        "available": True,
        "total_rows": total,
        "covered_rows": covered,
        "missing_rows": total - covered,
        "distinct_missing_symbols": len(missing_originals),
        "sample_missing_symbols": missing_originals[:20],
        "coverage_rate": rate,
        "alias_applied_rows": alias_applied_rows,
        "alias_covered_rows": alias_covered_rows,
        "distinct_aliases_used": alias_summary["distinct_aliases_used"],
        "alias_pairs": alias_summary["alias_pairs"],
    }

    if alias_applied_rows:
        findings.append(_finding(
            "info", "aliases_applied",
            f"Applied {alias_summary['distinct_aliases_used']} share-class "
            f"alias(es) to {alias_applied_rows} holding row(s). "
            f"{alias_covered_rows} now match the scored universe via an alias.",
            alias_applied_rows=alias_applied_rows,
            alias_covered_rows=alias_covered_rows,
            alias_pairs=alias_summary["alias_pairs"],
        ))

    if rate < threshold:
        findings.append(_finding(
            "warning", "low_universe_coverage",
            f"Only {rate * 100:.1f}% of model holdings match the scored fund "
            f"universe (threshold {threshold * 100:.0f}%) after applying "
            f"{alias_applied_rows} alias row(s). "
            f"{len(missing_originals)} distinct symbol(s) are still not scored.",
            coverage_rate=rate, threshold=threshold,
            distinct_missing_symbols=len(missing_originals),
            sample=missing_originals[:10],
        ))
    return findings, stats


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_model_holdings_dataframe(
    df: pd.DataFrame,
    *,
    dual_score_symbols: Optional[Iterable[str]] = None,
    source: Optional[str] = None,
    weight_tolerance: float = WEIGHT_SUM_TOLERANCE,
    min_coverage: float = DEFAULT_MIN_COVERAGE_WARN,
    alias_map: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Validate an in-memory model-holdings DataFrame.

    ``dual_score_symbols`` — iterable of symbols present in the scored
    universe. When supplied we report coverage / flag missing symbols.

    ``alias_map`` — optional Original->Scoring symbol map. Applied before the
    coverage check so share-class mismatches (e.g. PRBLX -> PRILX) don't
    count as missing. Defaults to ``load_default_aliases()`` when omitted.
    """
    if alias_map is None:
        alias_map = load_default_aliases()
    findings: List[Dict[str, Any]] = []

    col_findings = _check_required_columns(df)
    findings.extend(col_findings)

    # Cheap checks can still run even if some required columns are missing
    # (we just skip checks whose columns aren't present).
    findings.extend(_check_symbols_present(df))
    findings.extend(_check_model_name_present(df))
    findings.extend(_check_weight_parseability(df))
    findings.extend(_check_duplicate_model_symbol(df))

    weight_findings, weight_sums = _check_weight_sums(df, tolerance=weight_tolerance)
    findings.extend(weight_findings)

    coverage_findings, coverage_stats = _check_coverage(
        df, dual_score_symbols, threshold=min_coverage, alias_map=alias_map,
    )
    findings.extend(coverage_findings)

    model_names: List[str] = []
    if "Model_Name" in df.columns:
        model_names = sorted(
            {
                str(m).strip()
                for m in df["Model_Name"].dropna().astype(str)
                if str(m).strip()
            }
        )

    holding_count = int(len(df))
    findings.append(_finding(
        "info", "row_count",
        f"Holdings row count: {holding_count} across {len(model_names)} model(s)",
        holdings=holding_count, models=len(model_names),
    ))

    failed = any(f["severity"] == "error" for f in findings)
    counts = {
        "error": sum(1 for f in findings if f["severity"] == "error"),
        "warning": sum(1 for f in findings if f["severity"] == "warning"),
        "info": sum(1 for f in findings if f["severity"] == "info"),
    }
    return {
        "source": source,
        "row_count": holding_count,
        "column_count": int(df.shape[1]),
        "columns": list(df.columns),
        "required_columns": list(REQUIRED_COLUMNS),
        "optional_columns": list(OPTIONAL_COLUMNS),
        "model_names": model_names,
        "weight_sums_by_model": weight_sums,
        "coverage": coverage_stats,
        "findings": findings,
        "finding_counts": counts,
        "failed": failed,
    }


def _read_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=True)


def validate_model_holdings_file(
    path: str,
    *,
    dual_score_symbols: Optional[Iterable[str]] = None,
    weight_tolerance: float = WEIGHT_SUM_TOLERANCE,
    min_coverage: float = DEFAULT_MIN_COVERAGE_WARN,
    alias_map: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {
            "source": path,
            "failed": True,
            "finding_counts": {"error": 1, "warning": 0, "info": 0},
            "findings": [_finding(
                "error", "file_not_found", f"File does not exist: {path}"
            )],
        }
    try:
        df = _read_csv(path)
    except Exception as exc:  # pragma: no cover - pandas pass-through
        return {
            "source": path,
            "failed": True,
            "finding_counts": {"error": 1, "warning": 0, "info": 0},
            "findings": [_finding(
                "error", "csv_read_error", f"Could not read CSV: {exc}"
            )],
        }
    return validate_model_holdings_dataframe(
        df,
        dual_score_symbols=dual_score_symbols,
        source=path,
        weight_tolerance=weight_tolerance,
        min_coverage=min_coverage,
        alias_map=alias_map,
    )


def summarize(report: Dict[str, Any]) -> str:
    """Render a human-readable summary (mirrors ycharts_intake.summarize)."""
    lines: List[str] = []
    lines.append("=== Model Holdings Intake ===")
    lines.append(f"  source: {report.get('source')}")
    lines.append(
        f"  rows: {report.get('row_count')}  "
        f"cols: {report.get('column_count')}  "
        f"models: {len(report.get('model_names') or [])}"
    )
    counts = report.get("finding_counts", {})
    lines.append(
        f"  findings: {counts.get('error', 0)} error, "
        f"{counts.get('warning', 0)} warning, {counts.get('info', 0)} info"
    )
    lines.append(f"  status: {'FAIL' if report.get('failed') else 'PASS'}")
    weight_sums = report.get("weight_sums_by_model") or {}
    if weight_sums:
        lines.append("  weight sums:")
        for model, total in sorted(weight_sums.items()):
            lines.append(f"    {model}: {float(total) * 100:.2f}%")
    coverage = report.get("coverage") or {}
    if coverage.get("available"):
        lines.append(
            f"  universe coverage: {coverage['covered_rows']}/"
            f"{coverage['total_rows']} rows "
            f"({coverage['coverage_rate'] * 100:.1f}%)"
        )
        alias_rows = coverage.get("alias_applied_rows") or 0
        if alias_rows:
            pairs = coverage.get("alias_pairs") or []
            lines.append(
                f"  aliases applied: {alias_rows} row(s) via "
                f"{coverage.get('distinct_aliases_used', 0)} alias(es)"
            )
            for p in pairs:
                lines.append(f"    {p['original']} -> {p['scoring']}")
    for f in report.get("findings", []):
        sev = f["severity"].upper().ljust(7)
        lines.append(f"    [{sev}] {f['code']}: {f['message']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a model holdings CSV for the FundScore overlay.",
    )
    parser.add_argument("--path", required=True, help="Model holdings CSV.")
    parser.add_argument(
        "--dual-score-table", default=None,
        help="Optional: dual_score_table.csv to check symbol coverage against.",
    )
    parser.add_argument(
        "--alias-csv", default=None,
        help=(
            "Optional: CSV with columns Original_Symbol,Scoring_Symbol,Reason "
            "to extend the default share-class alias map."
        ),
    )
    parser.add_argument(
        "--json-out", default=None,
        help="If set, write the full report to this path.",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress the human-readable summary.",
    )
    args = parser.parse_args(argv)

    dual_symbols: Optional[List[str]] = None
    if args.dual_score_table:
        try:
            dst = pd.read_csv(args.dual_score_table, usecols=["Symbol"])
            dual_symbols = dst["Symbol"].dropna().astype(str).tolist()
        except Exception as exc:
            print(f"warning: could not read dual_score_table: {exc}")

    alias_map = load_default_aliases(extra_path=args.alias_csv)

    report = validate_model_holdings_file(
        args.path, dual_score_symbols=dual_symbols, alias_map=alias_map,
    )
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(report, f, indent=2, sort_keys=True, default=str)
    if not args.quiet:
        print(summarize(report))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(_cli())
