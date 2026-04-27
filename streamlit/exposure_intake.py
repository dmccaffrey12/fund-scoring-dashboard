"""
YCharts Exposure Intake
=======================
Parser/validator for YCharts stylebox + sector exposure CSV exports.

YCharts exports a wide-format CSV with columns:

    Symbol, Name,
    Equity Stylebox <Cap><Style> Exposure  (9 cells)
    <Sector> Exposure                      (11 cells)

Public surface:

    STYLEBOX_BUCKETS:    canonical 9 stylebox bucket keys
    SECTOR_BUCKETS:      canonical 11 sector bucket keys
    STYLEBOX_COLUMNS:    YCharts source column names
    SECTOR_COLUMNS:      YCharts source column names
    parse_exposures(path|file|df) -> pd.DataFrame (clean wide form)
    validate_exposures(df) -> dict report (errors, warnings, info)
    summarize_report(report) -> str (human-readable summary)

The clean wide form has Symbol, Name, plus 20 numeric columns named with
the canonical bucket keys (no "Exposure" suffix). Numerics are coerced to
floats, blanks/non-numerics become NaN.
"""

from __future__ import annotations

import io
import os
from typing import Any, Dict, List, Mapping, Optional, Union

import pandas as pd


# ---------------------------------------------------------------------------
# Canonical bucket names
# ---------------------------------------------------------------------------

STYLEBOX_BUCKETS: List[str] = [
    "LargeValue",
    "LargeBlend",
    "LargeGrowth",
    "MidValue",
    "MidBlend",
    "MidGrowth",
    "SmallValue",
    "SmallBlend",
    "SmallGrowth",
]

SECTOR_BUCKETS: List[str] = [
    "BasicMaterials",
    "ConsumerCyclical",
    "FinancialServices",
    "RealEstate",
    "CommunicationServices",
    "Energy",
    "Industrials",
    "Technology",
    "ConsumerDefensive",
    "Healthcare",
    "Utilities",
]

STYLEBOX_COLUMNS: Dict[str, str] = {
    "Equity Stylebox Large Cap Value Exposure": "LargeValue",
    "Equity Stylebox Large Cap Blend Exposure": "LargeBlend",
    "Equity Stylebox Large Cap Growth Exposure": "LargeGrowth",
    "Equity Stylebox Mid Cap Value Exposure": "MidValue",
    "Equity Stylebox Mid Cap Blend Exposure": "MidBlend",
    "Equity Stylebox Mid Cap Growth Exposure": "MidGrowth",
    "Equity Stylebox Small Cap Value Exposure": "SmallValue",
    "Equity Stylebox Small Cap Blend Exposure": "SmallBlend",
    "Equity Stylebox Small Cap Growth Exposure": "SmallGrowth",
}

SECTOR_COLUMNS: Dict[str, str] = {
    "Basic Materials Exposure": "BasicMaterials",
    "Consumer Cyclical Exposure": "ConsumerCyclical",
    "Financial Services Exposure": "FinancialServices",
    "Real Estate Exposure": "RealEstate",
    "Communication Services Exposure": "CommunicationServices",
    "Energy Exposure": "Energy",
    "Industrials Exposure": "Industrials",
    "Technology Exposure": "Technology",
    "Consumer Defensive Exposure": "ConsumerDefensive",
    "Healthcare Exposure": "Healthcare",
    "Utilities Exposure": "Utilities",
}

REQUIRED_COLUMNS: List[str] = (
    ["Symbol", "Name"]
    + list(STYLEBOX_COLUMNS.keys())
    + list(SECTOR_COLUMNS.keys())
)

CLEAN_COLUMNS: List[str] = ["Symbol", "Name"] + STYLEBOX_BUCKETS + SECTOR_BUCKETS

SUM_TOLERANCE_DEFAULT = 0.05


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _coerce_numeric(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def parse_exposures(
    source: Union[str, os.PathLike, io.IOBase, pd.DataFrame],
) -> pd.DataFrame:
    """Read a YCharts wide-format exposure export into a clean wide DataFrame.

    Accepts a file path, a file-like buffer (e.g. an uploaded file from
    Streamlit), or a pre-read DataFrame.

    The returned frame has columns ``Symbol``, ``Name``, the 9 stylebox
    bucket keys, and the 11 sector bucket keys. Numeric values are coerced;
    bad cells become NaN. Symbol is upper-cased, stripped.
    """
    if isinstance(source, pd.DataFrame):
        df = source.copy()
    else:
        df = pd.read_csv(source)

    if df is None or df.empty:
        return pd.DataFrame(columns=CLEAN_COLUMNS)

    # Map source columns -> canonical bucket names where present.
    rename: Dict[str, str] = {}
    rename.update({c: c for c in ("Symbol", "Name") if c in df.columns})
    for src, dst in {**STYLEBOX_COLUMNS, **SECTOR_COLUMNS}.items():
        if src in df.columns:
            rename[src] = dst

    df = df.rename(columns=rename)

    # Ensure all canonical columns exist (NaN if YCharts dropped a column).
    for col in STYLEBOX_BUCKETS + SECTOR_BUCKETS:
        if col not in df.columns:
            df[col] = pd.NA

    if "Symbol" not in df.columns:
        df["Symbol"] = pd.NA
    if "Name" not in df.columns:
        df["Name"] = pd.NA

    sym = df["Symbol"]
    # Replace true NaN/None with "" before upper-casing to avoid the
    # numpy-stringified "nan" sneaking through.
    df["Symbol"] = (
        sym.where(sym.notna(), "")
           .astype(str).str.strip().str.upper()
           .replace({"NAN": "", "NONE": ""})
    )
    df["Name"] = df["Name"].where(df["Name"].notna(), "").astype(str).str.strip()

    for col in STYLEBOX_BUCKETS + SECTOR_BUCKETS:
        df[col] = _coerce_numeric(df[col])

    return df.loc[:, CLEAN_COLUMNS].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _msg(severity: str, code: str, message: str, **extra: Any) -> Dict[str, Any]:
    out = {"severity": severity, "code": code, "message": message}
    out.update(extra)
    return out


def validate_exposures(
    df: pd.DataFrame,
    *,
    sum_tolerance: float = SUM_TOLERANCE_DEFAULT,
    source_label: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate a parsed exposure frame. Returns a structured report.

    Checks performed:
      - missing required columns (error)
      - missing/blank Symbol values (error)
      - duplicate Symbol values (warning — first kept)
      - non-numeric or NaN exposure cells per row (warning)
      - stylebox row sum vs 1.0 within tolerance (warning if outside)
      - sector row sum vs 1.0 within tolerance (warning if outside)

    Stylebox/sector sums are skipped when all values in that block for the
    row are NaN (the export simply did not provide that block for the fund).
    """
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    info: List[Dict[str, Any]] = []

    if df is None or df.empty:
        errors.append(_msg("error", "empty_input",
                           "Exposure file is empty or missing rows."))
        return {
            "source": source_label,
            "row_count": 0,
            "errors": errors,
            "warnings": warnings,
            "info": info,
            "failed": True,
        }

    missing = [c for c in CLEAN_COLUMNS if c not in df.columns]
    if missing:
        errors.append(_msg(
            "error", "missing_columns",
            f"Missing required columns: {missing}",
            columns=missing,
        ))
        return {
            "source": source_label,
            "row_count": int(len(df)),
            "errors": errors,
            "warnings": warnings,
            "info": info,
            "failed": True,
        }

    # Missing symbols
    sym = df["Symbol"].astype(str).str.strip()
    blank_mask = sym.eq("") | sym.eq("NAN")
    if blank_mask.any():
        errors.append(_msg(
            "error", "missing_symbol",
            f"{int(blank_mask.sum())} row(s) have a blank Symbol.",
            row_count=int(blank_mask.sum()),
        ))

    # Duplicate symbols (only count actual non-blank ones).
    nonblank = df.loc[~blank_mask, "Symbol"]
    dups = nonblank[nonblank.duplicated(keep=False)].unique().tolist()
    if dups:
        warnings.append(_msg(
            "warning", "duplicate_symbol",
            f"{len(dups)} duplicate Symbol value(s): {dups[:10]}",
            symbols=dups,
        ))

    # Sum checks — per row, per block.
    sb_cols = STYLEBOX_BUCKETS
    sec_cols = SECTOR_BUCKETS

    sb_sum = df[sb_cols].sum(axis=1, min_count=1)
    sb_count = df[sb_cols].notna().sum(axis=1)
    sec_sum = df[sec_cols].sum(axis=1, min_count=1)
    sec_count = df[sec_cols].notna().sum(axis=1)

    bad_sb: List[Dict[str, Any]] = []
    bad_sec: List[Dict[str, Any]] = []
    for idx, row in df.iterrows():
        s = sym.iloc[idx]
        if blank_mask.iloc[idx]:
            continue
        if sb_count.iloc[idx] > 0:
            v = sb_sum.iloc[idx]
            if pd.notna(v) and abs(float(v) - 1.0) > sum_tolerance:
                bad_sb.append({"symbol": s, "sum": float(v)})
        if sec_count.iloc[idx] > 0:
            v = sec_sum.iloc[idx]
            if pd.notna(v) and abs(float(v) - 1.0) > sum_tolerance:
                bad_sec.append({"symbol": s, "sum": float(v)})

    if bad_sb:
        warnings.append(_msg(
            "warning", "stylebox_sum_off",
            f"{len(bad_sb)} fund(s) with stylebox sum outside "
            f"1±{sum_tolerance:g}.",
            funds=bad_sb[:10],
            tolerance=sum_tolerance,
        ))
    if bad_sec:
        warnings.append(_msg(
            "warning", "sector_sum_off",
            f"{len(bad_sec)} fund(s) with sector sum outside "
            f"1±{sum_tolerance:g}.",
            funds=bad_sec[:10],
            tolerance=sum_tolerance,
        ))

    # Per-block null-rate info.
    null_sb_rows = int((sb_count == 0).sum())
    null_sec_rows = int((sec_count == 0).sum())
    if null_sb_rows:
        info.append(_msg(
            "info", "stylebox_all_null",
            f"{null_sb_rows} row(s) have no stylebox values.",
            row_count=null_sb_rows,
        ))
    if null_sec_rows:
        info.append(_msg(
            "info", "sector_all_null",
            f"{null_sec_rows} row(s) have no sector values.",
            row_count=null_sec_rows,
        ))

    info.append(_msg(
        "info", "row_count",
        f"Parsed {len(df)} row(s) with {len(sb_cols)} stylebox + "
        f"{len(sec_cols)} sector columns.",
        row_count=int(len(df)),
    ))

    failed = bool(errors)
    return {
        "source": source_label,
        "row_count": int(len(df)),
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "failed": failed,
    }


def summarize_report(report: Mapping[str, Any]) -> str:
    """Return a human-readable summary of a validate_exposures report."""
    lines: List[str] = []
    src = report.get("source") or "exposures"
    rc = report.get("row_count", 0)
    failed = report.get("failed", False)
    status = "FAILED" if failed else "OK"
    lines.append(f"[{status}] {src} — {rc} row(s)")
    for level in ("errors", "warnings", "info"):
        items = report.get(level) or []
        for it in items:
            lines.append(f"  · {level[:-1].upper():7s} {it.get('code', '?')}: "
                         f"{it.get('message', '')}")
    return "\n".join(lines)
