"""
Replacement-Candidate List Intake
=================================
Parser/validator for the **committee candidate list** — a simple, lightly-
schema'd CSV the user uploads to specify the actual names under
consideration for replacing a model holding (e.g. PRBLX).

This is intentionally distinct from the YCharts exposure intake
(``exposure_intake.parse_exposures``):

    * Exposure files are wide-format with 9 stylebox + 11 sector columns
      and feed the **benchmark-fit / portfolio-alignment** layer.
    * Candidate-list files are minimal — just a symbol column plus any
      optional metadata the user wants preserved (Name, Notes, Rationale,
      Active/Passive, Fund Type, Category). They define the **authoritative
      universe** for the staff-facing replacement short list and the
      printable brief.

Accepted symbol header names (case-insensitive, leading/trailing whitespace
ignored): ``Symbol``, ``Ticker``, ``Fund Symbol``, ``Candidate Symbol``.

Public API:
    SYMBOL_HEADER_ALIASES — recognised symbol column names (lower-cased)
    OPTIONAL_PASSTHROUGH_HEADERS — optional metadata we keep when present
    parse_candidate_list(source) -> pd.DataFrame
    validate_candidate_list(df, *, source_label=None) -> dict report
    summarize_report(report) -> str
    candidate_list_template_csv() -> str

The parsed frame has columns: ``Symbol`` (upper-cased, stripped) plus any
of the optional metadata columns the user supplied, normalized to canonical
``Name`` / ``Fund_Name`` / ``Notes`` / ``Rationale`` / ``Active_Passive`` /
``Fund_Type`` / ``Category`` names where recognised. Unknown columns are
preserved as-is so the user's original notes survive the round trip.
"""

from __future__ import annotations

import io
import os
from typing import Any, Dict, List, Mapping, Optional, Union

import pandas as pd


# ---------------------------------------------------------------------------
# Header recognition
# ---------------------------------------------------------------------------

# Lower-cased, whitespace-collapsed forms we'll treat as the symbol column.
SYMBOL_HEADER_ALIASES: Dict[str, str] = {
    "symbol": "Symbol",
    "ticker": "Symbol",
    "fund symbol": "Symbol",
    "candidate symbol": "Symbol",
    "fund_symbol": "Symbol",
    "candidate_symbol": "Symbol",
}

# Optional pass-through headers — case/whitespace-insensitive on the input,
# normalised to a canonical name on the output.
OPTIONAL_PASSTHROUGH_HEADERS: Dict[str, str] = {
    "name": "Name",
    "fund name": "Name",
    "fund_name": "Fund_Name",
    "notes": "Notes",
    "note": "Notes",
    "rationale": "Rationale",
    "active_passive": "Active_Passive",
    "active/passive": "Active_Passive",
    "active passive": "Active_Passive",
    "fund_type": "Fund_Type",
    "fund type": "Fund_Type",
    "category": "Category",
    "morningstar category": "Category",
}


# Columns we always emit at the front of the parsed frame, in order, when
# present on the source.
PREFERRED_COLUMN_ORDER: List[str] = [
    "Symbol",
    "Name",
    "Fund_Name",
    "Category",
    "Fund_Type",
    "Active_Passive",
    "Notes",
    "Rationale",
]


def _norm_header(s: Any) -> str:
    if s is None:
        return ""
    return str(s).strip().lower().replace("  ", " ")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_candidate_list(
    source: Union[str, os.PathLike, io.IOBase, pd.DataFrame],
) -> pd.DataFrame:
    """Read a committee candidate-list CSV into a clean DataFrame.

    Accepts a path, a file-like object (e.g. a Streamlit upload), or an
    already-parsed DataFrame. Symbol column header is matched case-
    insensitively against ``SYMBOL_HEADER_ALIASES``. The returned frame
    has at minimum a ``Symbol`` column (upper-cased, stripped, blanks
    dropped). Recognised optional columns are renamed to their canonical
    forms; unknown columns are preserved as-is so user-supplied notes are
    not lost.

    Raises ValueError when no symbol column can be located.
    """
    if isinstance(source, pd.DataFrame):
        df = source.copy()
    else:
        df = pd.read_csv(
            source,
            skip_blank_lines=True,
            on_bad_lines="skip",
        )

    if df is None or df.empty:
        return pd.DataFrame(columns=["Symbol"])

    # Build a rename map: input header -> canonical output header.
    rename: Dict[str, str] = {}
    seen_symbol = False
    for col in list(df.columns):
        key = _norm_header(col)
        if not seen_symbol and key in SYMBOL_HEADER_ALIASES:
            rename[col] = SYMBOL_HEADER_ALIASES[key]
            seen_symbol = True
            continue
        if key in OPTIONAL_PASSTHROUGH_HEADERS:
            rename[col] = OPTIONAL_PASSTHROUGH_HEADERS[key]

    if not seen_symbol:
        raise ValueError(
            "Candidate list CSV must include a symbol column. "
            f"Recognised header names (case-insensitive): "
            f"{sorted(set(SYMBOL_HEADER_ALIASES.keys()))}. "
            f"Got columns: {list(df.columns)}"
        )

    df = df.rename(columns=rename)

    sym = df["Symbol"]
    df["Symbol"] = (
        sym.where(sym.notna(), "")
           .astype(str).str.strip().str.upper()
           .replace({"NAN": "", "NONE": ""})
    )
    # Drop blank-symbol rows entirely — they cannot anchor a candidate.
    df = df.loc[df["Symbol"] != ""].copy()

    # Drop duplicate symbols, keeping first occurrence so user-supplied
    # ordering / first-seen Name wins.
    df = df.drop_duplicates(subset=["Symbol"], keep="first").reset_index(drop=True)

    # Re-order so canonical columns lead, with everything else preserved.
    leading = [c for c in PREFERRED_COLUMN_ORDER if c in df.columns]
    trailing = [c for c in df.columns if c not in leading]
    return df.loc[:, leading + trailing].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _msg(severity: str, code: str, message: str, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"severity": severity, "code": code, "message": message}
    out.update(extra)
    return out


def validate_candidate_list(
    df: pd.DataFrame,
    *,
    source_label: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate a parsed candidate-list frame. Returns a structured report.

    Checks:
        - missing/blank Symbol values (error — these are dropped at parse
          time, but we report the count if the caller hands us a frame
          that still has them)
        - duplicate Symbol values (warning — first kept)
        - empty list after parsing (error)

    The report mirrors the shape of ``exposure_intake.validate_exposures``
    so the Streamlit page can reuse the same summary helper.
    """
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    info: List[Dict[str, Any]] = []

    if df is None or df.empty:
        errors.append(_msg(
            "error", "empty_input",
            "Candidate list is empty — at least one candidate symbol is required.",
        ))
        return {
            "source": source_label,
            "row_count": 0,
            "errors": errors,
            "warnings": warnings,
            "info": info,
            "failed": True,
        }

    if "Symbol" not in df.columns:
        errors.append(_msg(
            "error", "missing_symbol_column",
            "Parsed frame is missing the canonical 'Symbol' column.",
        ))
        return {
            "source": source_label,
            "row_count": int(len(df)),
            "errors": errors,
            "warnings": warnings,
            "info": info,
            "failed": True,
        }

    sym = df["Symbol"].astype(str).str.strip()
    blank = sym.eq("") | sym.str.upper().eq("NAN")
    if blank.any():
        errors.append(_msg(
            "error", "missing_symbol",
            f"{int(blank.sum())} row(s) have a blank Symbol.",
            row_count=int(blank.sum()),
        ))

    dup = sym[sym.duplicated(keep=False) & ~blank].unique().tolist()
    if dup:
        warnings.append(_msg(
            "warning", "duplicate_symbol",
            f"{len(dup)} duplicate symbol(s) — first occurrence kept: "
            f"{dup[:10]}",
            symbols=dup,
        ))

    info.append(_msg(
        "info", "row_count",
        f"Parsed {int(len(df))} candidate symbol(s).",
        row_count=int(len(df)),
    ))

    optional_present = [
        c for c in PREFERRED_COLUMN_ORDER if c in df.columns and c != "Symbol"
    ]
    if optional_present:
        info.append(_msg(
            "info", "optional_columns",
            f"Optional metadata preserved: {optional_present}",
            columns=optional_present,
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
    """Human-readable summary, parallel to ``exposure_intake.summarize_report``."""
    lines: List[str] = []
    src = report.get("source") or "candidate_list"
    rc = report.get("row_count", 0)
    failed = report.get("failed", False)
    status = "FAILED" if failed else "OK"
    lines.append(f"[{status}] {src} — {rc} candidate symbol(s)")
    for level in ("errors", "warnings", "info"):
        items = report.get(level) or []
        for it in items:
            lines.append(
                f"  · {level[:-1].upper():7s} {it.get('code', '?')}: "
                f"{it.get('message', '')}"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Downloadable template
# ---------------------------------------------------------------------------

CANDIDATE_LIST_TEMPLATE_HEADER: List[str] = [
    "Symbol", "Name", "Active_Passive", "Fund_Type", "Category",
    "Notes", "Rationale",
]

CANDIDATE_LIST_TEMPLATE_ROWS: List[List[str]] = [
    ["AGIZX", "Alger Growth & Income Fund Z", "Active", "Mutual Fund",
     "Large Blend", "", "Quality-led; replace PRBLX"],
    ["AVLC", "Avantis US Large Cap Equity ETF", "Active", "ETF",
     "Large Blend", "", "Factor-tilted; reasonable expense ratio"],
    ["FCEUX", "Franklin U.S. Core Equity Advisor", "Active", "Mutual Fund",
     "Large Blend", "", ""],
]


def candidate_list_template_csv() -> str:
    """Return a downloadable CSV string showing the minimum schema."""
    rows = [",".join(CANDIDATE_LIST_TEMPLATE_HEADER)]
    for row in CANDIDATE_LIST_TEMPLATE_ROWS:
        rows.append(",".join(row))
    return "\n".join(rows) + "\n"


# ---------------------------------------------------------------------------
# Helper for downstream consumers
# ---------------------------------------------------------------------------

def candidate_symbol_name_map(df: pd.DataFrame) -> Dict[str, str]:
    """Return {upper_symbol: name} from a parsed candidate-list frame.

    Falls back to ``Fund_Name`` when ``Name`` is missing for a row.
    Empty entries are excluded so callers can ``or`` against another
    name source without overwriting with blanks.
    """
    out: Dict[str, str] = {}
    if df is None or df.empty or "Symbol" not in df.columns:
        return out
    name_col = None
    if "Name" in df.columns:
        name_col = "Name"
    elif "Fund_Name" in df.columns:
        name_col = "Fund_Name"
    for i, sym in enumerate(df["Symbol"].astype(str).str.upper().tolist()):
        if not sym:
            continue
        if name_col is not None:
            n = df[name_col].iloc[i]
            if isinstance(n, str) and n.strip():
                out[sym] = n.strip()
            elif n is not None and not (isinstance(n, float) and pd.isna(n)):
                s = str(n).strip()
                if s:
                    out[sym] = s
    return out
