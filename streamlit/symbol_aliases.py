"""
Symbol Aliases
==============
Share-class reconciliation for the model-holdings overlay.

The scored universe produced by ``dual_score_table`` applies YCharts' duplicate
removal, which keeps a single representative per fund (typically the retail or
institutional share class). Real-world model holdings are frequently recorded
in a *different* share class for the same underlying fund — e.g. a model may
track ``PRBLX`` while the scored universe contains ``PRILX`` (Parnassus Core
Equity).

This module preserves the committee-facing original Symbol from the model
library but lets the overlay join on a reconciled ``Scoring_Symbol``. Raw user
CSVs are never edited — reconciliation is a config layer.

Resolution order (first match wins):
    1. A symbol that already appears in the scored universe is left alone.
    2. Symbols present in the alias map are rewritten to their ``Scoring_Symbol``.
    3. Everything else is passed through unchanged (and will surface as
       ``Review_Missing_Score`` in the overlay, as before).

Public API:
    DEFAULT_ALIASES          — baked-in mappings that ship with the repo.
    DEFAULT_ALIAS_CSV_PATH   — location of the editable CSV default.
    load_default_aliases()   — returns DEFAULT_ALIASES merged with the CSV.
    load_aliases_from_csv()  — parse an alias CSV (raises on bad schema).
    apply_aliases(df, ...)   — add Original_Symbol / Scoring_Symbol /
                               Alias_Applied columns to a holdings frame.

Alias CSV schema:
    Required columns: Original_Symbol, Scoring_Symbol
    Optional column:  Reason (free-text, audit trail only)
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Mapping, Optional

import pandas as pd


_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
DEFAULT_ALIAS_CSV_PATH = os.path.join(_CONFIG_DIR, "symbol_aliases.csv")

# Baked-in defaults. These match the share-class dedupe performed by the 2025
# YCharts ingest: the committee-visible model symbol stays intact, the scoring
# join uses the deduped universe representative.
DEFAULT_ALIASES: Dict[str, str] = {
    "PRBLX": "PRILX",  # Parnassus Core Equity — dedupe kept institutional share class
    "GSTKX": "GSIKX",  # GS Small Cap Growth Insights — dedupe kept institutional share class
    "PONPX": "PIMIX",  # PIMCO Income — dedupe kept institutional share class
    "FECMX": "FEMKX",  # Fidelity Emerging Markets — dedupe kept oldest share class
}


REQUIRED_ALIAS_COLUMNS: List[str] = ["Original_Symbol", "Scoring_Symbol"]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _normalize_symbol(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip().upper()


def load_aliases_from_csv(path: str) -> Dict[str, str]:
    """Parse an alias CSV and return an Original->Scoring dict.

    Raises FileNotFoundError if ``path`` doesn't exist, and ValueError when
    the file is missing required columns or is structurally bad.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Alias CSV not found: {path}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in REQUIRED_ALIAS_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Alias CSV {path} missing required columns: {missing}. "
            f"Required: {REQUIRED_ALIAS_COLUMNS}"
        )
    mapping: Dict[str, str] = {}
    for _, row in df.iterrows():
        orig = _normalize_symbol(row.get("Original_Symbol"))
        target = _normalize_symbol(row.get("Scoring_Symbol"))
        if not orig or not target:
            continue
        if orig == target:
            continue
        mapping[orig] = target
    return mapping


def load_default_aliases(
    extra_path: Optional[str] = None,
) -> Dict[str, str]:
    """Return the default alias map.

    Merges, in order: ``DEFAULT_ALIASES`` (always), the CSV at
    ``DEFAULT_ALIAS_CSV_PATH`` if present, and ``extra_path`` if supplied.
    Later sources override earlier ones so teams can shadow the baked-in
    defaults without code edits.
    """
    merged: Dict[str, str] = dict(DEFAULT_ALIASES)
    if os.path.isfile(DEFAULT_ALIAS_CSV_PATH):
        try:
            merged.update(load_aliases_from_csv(DEFAULT_ALIAS_CSV_PATH))
        except ValueError:
            pass
    if extra_path:
        merged.update(load_aliases_from_csv(extra_path))
    return merged


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

def resolve_symbol(
    symbol: Any,
    alias_map: Mapping[str, str],
    universe: Optional[Iterable[str]] = None,
) -> str:
    """Return the scoring symbol for ``symbol``.

    When ``universe`` is provided, a symbol already in the universe is
    returned unchanged (aliases don't override an otherwise-valid ticker).
    """
    norm = _normalize_symbol(symbol)
    if not norm:
        return ""
    if universe is not None and norm in universe:
        return norm
    return alias_map.get(norm, norm)


def apply_aliases(
    df: pd.DataFrame,
    alias_map: Optional[Mapping[str, str]] = None,
    *,
    universe: Optional[Iterable[str]] = None,
    symbol_col: str = "Symbol",
) -> pd.DataFrame:
    """Return a copy of ``df`` with alias resolution applied.

    Adds three columns (preserving ``symbol_col`` as the committee-visible
    original):
        Original_Symbol  — copy of the input Symbol, uppercased + stripped.
        Scoring_Symbol   — symbol used to join against the scored universe.
        Alias_Applied    — bool flag, true when Scoring_Symbol != Original_Symbol.

    ``alias_map`` defaults to ``load_default_aliases()`` when omitted.
    """
    out = df.copy()
    if symbol_col not in out.columns:
        return out

    if alias_map is None:
        alias_map = load_default_aliases()

    uni: Optional[set] = None
    if universe is not None:
        uni = {_normalize_symbol(s) for s in universe if _normalize_symbol(s)}

    originals = out[symbol_col].apply(_normalize_symbol)
    resolved = originals.apply(lambda s: resolve_symbol(s, alias_map, uni))

    out["Original_Symbol"] = originals
    out["Scoring_Symbol"] = resolved
    out["Alias_Applied"] = (originals != resolved) & (originals != "")
    return out


def summarize_alias_usage(
    df: pd.DataFrame,
    *,
    universe: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Return summary counts for an alias-resolved holdings frame.

    ``df`` is expected to already carry ``Original_Symbol`` / ``Scoring_Symbol``
    / ``Alias_Applied`` (as produced by ``apply_aliases``).
    """
    summary: Dict[str, Any] = {
        "total_rows": int(len(df)),
        "alias_applied_rows": 0,
        "distinct_aliases_used": 0,
        "alias_pairs": [],
        "still_unscored_symbols": [],
    }
    if df.empty or "Alias_Applied" not in df.columns:
        return summary

    alias_rows = df[df["Alias_Applied"] == True]  # noqa: E712
    summary["alias_applied_rows"] = int(len(alias_rows))
    pairs = (
        alias_rows[["Original_Symbol", "Scoring_Symbol"]]
        .drop_duplicates()
        .sort_values(["Original_Symbol", "Scoring_Symbol"])
    )
    summary["distinct_aliases_used"] = int(len(pairs))
    summary["alias_pairs"] = [
        {"original": r.Original_Symbol, "scoring": r.Scoring_Symbol}
        for r in pairs.itertuples(index=False)
    ]

    if universe is not None:
        uni = {_normalize_symbol(s) for s in universe if _normalize_symbol(s)}
        scoring = df["Scoring_Symbol"].astype(str).str.strip().str.upper()
        unscored = sorted(set(scoring[~scoring.isin(uni) & (scoring != "")]))
        summary["still_unscored_symbols"] = unscored

    return summary
