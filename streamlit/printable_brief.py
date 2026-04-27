"""
Printable Replacement Brief
===========================
Render a self-contained, printable HTML brief for a single replacement
research result. Drives the staff/committee paper-or-PDF workflow when
Streamlit Cloud's run-archive directory isn't reachable to the user.

Public API:
    render_printable_brief_html(result_or_loaded, *, run_date=None) -> str
    build_artifact_zip(loaded, *, html=None, zip_name=None) -> bytes

Design notes:
    * No Quarto / Jinja / pandoc dependency — Streamlit Cloud often lacks
      them. We build the HTML by hand with careful escaping.
    * Print CSS hides nav chrome and pages cleanly via browser "Print to
      PDF". The brief is also readable on-screen.
    * The function works from either a live ``ReplacementResult`` (in
      memory) or the dict produced by ``replacement_workbench.load_replacement``
      so the Streamlit page can render either path.
"""

from __future__ import annotations

import html
import io
import json
import math
import zipfile
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

import pandas as pd


# Streamlit Cloud's run dir is ephemeral — the brief embeds this caveat so
# anyone reviewing a printed copy understands the provenance constraint.
EPHEMERAL_STORAGE_NOTE = (
    "Streamlit Cloud run-archive storage is ephemeral — server-side paths "
    "such as <code>/mount/src/...</code> are not user-accessible and are "
    "wiped on redeploy. Save downloaded artifacts (this HTML, CSVs, the "
    "Markdown brief) to local committee records."
)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _result_to_dict(result_or_loaded: Any) -> Dict[str, Any]:
    """Accept either a ReplacementResult dataclass or a loaded dict."""
    if isinstance(result_or_loaded, Mapping):
        d = dict(result_or_loaded)
    elif is_dataclass(result_or_loaded):
        d = asdict(result_or_loaded)
        # asdict() loses DataFrame identity → re-attach from attributes.
        for attr in (
            "candidates",
            "current_profile",
            "benchmark_fit_candidates",
            "current_vs_benchmark",
            "replacement_delta",
        ):
            d[attr] = getattr(result_or_loaded, attr, pd.DataFrame())
        d["brief_markdown"] = getattr(result_or_loaded, "brief_markdown", "")
    else:
        raise TypeError(
            "render_printable_brief_html expects a ReplacementResult or a "
            f"loaded artifact dict; got {type(result_or_loaded)!r}."
        )

    # Provide safe defaults so downstream rendering doesn't have to branch.
    d.setdefault("candidates", pd.DataFrame())
    d.setdefault("current_profile", pd.DataFrame())
    d.setdefault("benchmark_fit_candidates", pd.DataFrame())
    d.setdefault("current_vs_benchmark", pd.DataFrame())
    d.setdefault("replacement_delta", pd.DataFrame())
    d.setdefault("summary", {})
    d.setdefault("brief_markdown", "")
    return d


def _esc(value: Any) -> str:
    """HTML-escape, gracefully rendering NaN / None as em-dashes."""
    if value is None:
        return "—"
    if isinstance(value, float) and math.isnan(value):
        return "—"
    s = str(value)
    if not s.strip() or s.lower() == "nan":
        return "—"
    return html.escape(s, quote=True)


def _fmt_float(value: Any, digits: int = 1) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and math.isnan(value):
        return "—"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return _esc(value)


def _fmt_int(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and math.isnan(value):
        return "—"
    try:
        return f"{int(float(value))}"
    except (TypeError, ValueError):
        return _esc(value)


def _fmt_pct(value: Any, digits: int = 0) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return _esc(value)


def _safe_get(row: Mapping[str, Any], key: str) -> Any:
    if key in row:
        return row[key]
    return None


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_header(
    summary: Mapping[str, Any],
    ticker: str,
    resolved_ticker: str,
    alias_applied: bool,
) -> str:
    run_date = summary.get("run_date") or "—"
    generated = summary.get("generated_at") or "—"
    alias_html = ""
    if alias_applied and resolved_ticker and resolved_ticker != ticker:
        alias_html = (
            f' <span class="alias">(resolved to '
            f"<code>{_esc(resolved_ticker)}</code> via share-class alias)</span>"
        )

    # Prominent candidate-universe banner so reviewers see the source at a
    # glance — the committee list, the candidate-exposures fallback, or
    # discovery mode.
    cu_source = summary.get("candidate_universe_source")
    inferred_cat = summary.get("inferred_category") or summary.get("category")
    inferred_ft = summary.get("inferred_fund_type")
    cat_used = bool(summary.get("category_filter_used"))
    ft_used = bool(summary.get("fund_type_filter_used"))
    ft_applied = summary.get("fund_type_filter")
    if cu_source == "committee_list":
        size = summary.get("committee_list_size") or 0
        filter_line = (
            "<br><span class=\"filter-line\"><strong>Discovery filters:</strong> "
            "<em>not forced</em> — committee list is authoritative "
            f"(inferred category <code>{_esc(inferred_cat or 'unknown')}</code>, "
            f"inferred fund type <code>{_esc(inferred_ft or 'unknown')}</code>)."
            "</span>"
        )
        banner = (
            '<p class="universe-banner committee">'
            "<strong>Candidate universe:</strong> uploaded committee "
            f"candidate list (<strong>{_esc(size)} symbol(s)</strong>) — "
            "this brief is scoped to the names you uploaded for "
            "committee review."
            f"{filter_line}"
            "</p>"
        )
    elif summary.get("restrict_to_candidate_exposures"):
        size = summary.get("candidate_universe_size") or 0
        applied_bits: List[str] = []
        if cat_used and inferred_cat:
            applied_bits.append(_esc(inferred_cat))
        if ft_used and ft_applied:
            applied_bits.append(_esc(ft_applied))
        applied_str = (
            " + ".join(applied_bits) if applied_bits else "<em>none</em>"
        )
        filter_line = (
            "<br><span class=\"filter-line\"><strong>Discovery filters:</strong> "
            f"{applied_str} (inferred category "
            f"<code>{_esc(inferred_cat or 'unknown')}</code>, "
            f"inferred fund type <code>{_esc(inferred_ft or 'unknown')}</code>)."
            "</span>"
        )
        banner = (
            '<p class="universe-banner uploaded">'
            "<strong>Candidate universe:</strong> uploaded candidate "
            f"exposures (<strong>{_esc(size)} symbol(s)</strong>)."
            f"{filter_line}"
            "</p>"
        )
    else:
        applied_bits = []
        if cat_used and inferred_cat:
            applied_bits.append(_esc(inferred_cat))
        if ft_used and ft_applied:
            applied_bits.append(_esc(ft_applied))
        applied_str = (
            " + ".join(applied_bits) if applied_bits else "<em>none</em>"
        )
        filter_line = (
            "<br><span class=\"filter-line\"><strong>Discovery filters:</strong> "
            f"{applied_str} (inferred category "
            f"<code>{_esc(inferred_cat or 'unknown')}</code>, "
            f"inferred fund type <code>{_esc(inferred_ft or 'unknown')}</code>)."
            "</span>"
        )
        banner = (
            '<p class="universe-banner discovery">'
            "<strong>Candidate universe:</strong> discovery mode — full "
            "scored universe in the same category. Upload a committee "
            "candidate list to scope this brief to the names actually "
            "under consideration."
            f"{filter_line}"
            "</p>"
        )

    return (
        '<header class="brief-header">'
        f"<h1>Replacement Brief — <code>{_esc(ticker)}</code>"
        f"{alias_html}</h1>"
        f'<p class="meta">Run date: <strong>{_esc(run_date)}</strong> '
        f"· Generated: {_esc(generated)}</p>"
        f"{banner}"
        "</header>"
    )


def _render_current_holding(
    profile: pd.DataFrame,
    summary: Mapping[str, Any],
    ticker: str,
    resolved_ticker: str,
    alias_applied: bool,
) -> str:
    if profile is None or profile.empty:
        return (
            '<section><h2>Current holding</h2>'
            f"<p>No profile available for <code>{_esc(ticker)}</code>.</p>"
            "</section>"
        )
    row = profile.iloc[0]
    rows = [
        ("Ticker (committee)", _esc(ticker)),
        (
            "Resolved scoring ticker",
            _esc(resolved_ticker) + (" (alias applied)" if alias_applied else ""),
        ),
        ("Name", _esc(_safe_get(row, "Name"))),
        (
            "Category",
            _esc(_safe_get(row, "Category"))
            + f" <span class=\"muted\">(source: {_esc(summary.get('category_source', '—'))})</span>",
        ),
        ("Fund type", _esc(_safe_get(row, "Fund_Type"))),
        ("Model", _esc(_safe_get(row, "Model_Name"))),
        ("Target weight", _fmt_float(_safe_get(row, "Target_Weight_Pct")) + "%"),
        (
            "2023 score",
            f"{_fmt_float(_safe_get(row, 'Score_2023_Final'))} "
            f"(rank {_fmt_int(_safe_get(row, 'Rank_2023'))}, "
            f"band {_esc(_safe_get(row, 'Score_Band_2023'))})",
        ),
        (
            "2025 score",
            f"{_fmt_float(_safe_get(row, 'Score_2025_Final'))} "
            f"(rank {_fmt_int(_safe_get(row, 'Rank_2025'))}, "
            f"band {_esc(_safe_get(row, 'Score_Band_2025'))})",
        ),
        (
            "Consensus rank · Quadrant",
            f"{_fmt_int(_safe_get(row, 'Consensus_Rank'))} "
            f"· {_esc(_safe_get(row, 'Quadrant'))}",
        ),
        ("Overlay action", _esc(_safe_get(row, "Overlay_Action"))),
    ]
    body = "".join(
        f"<tr><th>{label}</th><td>{value}</td></tr>"
        for label, value in rows
    )
    return (
        '<section><h2>Current holding</h2>'
        f'<table class="kv">{body}</table></section>'
    )


def _render_methodology(summary: Mapping[str, Any]) -> str:
    items: List[str] = []
    items.append(
        "Filter: <strong>same Morningstar category</strong> "
        f"(<code>{_esc(summary.get('category') or 'unknown')}</code>)."
    )
    cu_source = summary.get("candidate_universe_source")
    if cu_source == "committee_list":
        items.append(
            "Candidate universe: <strong>uploaded committee candidate "
            f"list</strong> ({_esc(summary.get('committee_list_size') or 0)} "
            "symbol(s)). This is the authoritative set of names under "
            "consideration for replacing the current holding — the full "
            "scored universe is <em>not</em> used for this staff-facing "
            "short list."
        )
        held_excl = summary.get("committee_list_excluded_held_symbols") or []
        if held_excl:
            items.append(
                "Held names excluded from the committee list: "
                + ", ".join(f"<code>{_esc(s)}</code>" for s in held_excl)
                + ". Toggle <em>Include already-held names</em> in the "
                "Streamlit page to retain them."
            )
        missing_scored = (
            summary.get("committee_list_missing_from_scored_universe") or []
        )
        if missing_scored:
            items.append(
                "Committee-list names not in the scored universe "
                "(included as un-scored rows): "
                + ", ".join(f"<code>{_esc(s)}</code>" for s in missing_scored)
            )
    elif summary.get("restrict_to_candidate_exposures"):
        items.append(
            "Candidate universe: <strong>uploaded curated candidate-exposures "
            f"file</strong> ({_esc(summary.get('candidate_universe_size') or 0)} "
            "symbol(s)). The full scored universe is not used for the staff-"
            "facing short list — only ideas screened upstream."
        )
    else:
        items.append(
            "Candidate universe: <strong>full scored universe</strong> "
            "in the same category (<em>discovery mode</em> — upload a "
            "committee candidate list to scope this brief to the names "
            "actually under consideration)."
        )
    items.append(
        "Ranking: <strong>Consensus_Rank</strong> (mean of 2023 and 2025 "
        "ranks), best first. 2023 and 2025 lenses are preserved side-by-"
        "side; disagreement appears as the <em>Reason / Fit</em> label and "
        "is never blended away."
    )
    if summary.get("exclude_already_held"):
        items.append(
            "Already-held positions are <strong>excluded</strong> by default "
            "— passive sleeve names like SPYM cannot be recommended as a "
            "replacement for an active holding sitting alongside them. The "
            "current holding being replaced is the only allowed exception."
        )
    else:
        items.append(
            "Other currently-held tickers are <strong>flagged</strong> "
            "(<em>Already_Held / Held_By_Models</em>) but kept in the list."
        )
    if summary.get("benchmark_fit_enabled"):
        bw = summary.get("benchmark_weights") or {}
        if bw:
            wstr = ", ".join(
                f"{_esc(k)} {_fmt_pct(v)}" for k, v in bw.items()
            )
            items.append(
                "Benchmark fit: drift = current model − benchmark, summed by "
                "stylebox + sector buckets. Static benchmark weights: "
                f"{wstr}."
            )
    return (
        '<section><h2>Methodology</h2><ul>'
        + "".join(f"<li>{item}</li>" for item in items)
        + "</ul></section>"
    )


def _candidate_columns_for_table() -> Sequence[Sequence[str]]:
    """Return (header, df_column) pairs for the top-candidates table."""
    return (
        ("#", "Rank"),
        ("Symbol", "Symbol"),
        ("Name", "Name"),
        ("Type", "Fund_Type"),
        ("2023", "Score_2023_Final"),
        ("2025", "Score_2025_Final"),
        ("Cons.", "Consensus_Rank"),
        ("Bands (23/25)", None),
        ("Reason / Fit", "Reason_Label"),
        ("Held?", None),
    )


def _render_candidates(candidates: pd.DataFrame) -> str:
    if candidates is None or candidates.empty:
        return (
            '<section><h2>Top candidates by FundScore</h2>'
            "<p>No same-category candidates were found for this run.</p>"
            "</section>"
        )

    header_cells: List[str] = []
    for label, _col in _candidate_columns_for_table():
        header_cells.append(f"<th>{_esc(label)}</th>")
    rows_html: List[str] = []
    for _, row in candidates.iterrows():
        bands = (
            f"{_esc(_safe_get(row, 'Score_Band_2023'))}/"
            f"{_esc(_safe_get(row, 'Score_Band_2025'))}"
        )
        held_flag = bool(_safe_get(row, "Already_Held"))
        held_models = _safe_get(row, "Held_By_Models")
        held_cell = (
            f"<span class=\"held\">held — {_esc(held_models)}</span>"
            if held_flag
            else "—"
        )
        cells = [
            f"<td>{_esc(_safe_get(row, 'Rank'))}</td>",
            f"<td><code>{_esc(_safe_get(row, 'Symbol'))}</code></td>",
            f"<td>{_esc(_safe_get(row, 'Name'))}</td>",
            f"<td>{_esc(_safe_get(row, 'Fund_Type'))}</td>",
            f"<td>{_fmt_float(_safe_get(row, 'Score_2023_Final'))}</td>",
            f"<td>{_fmt_float(_safe_get(row, 'Score_2025_Final'))}</td>",
            f"<td>{_fmt_int(_safe_get(row, 'Consensus_Rank'))}</td>",
            f"<td>{bands}</td>",
            f"<td>{_esc(_safe_get(row, 'Reason_Label'))}</td>",
            f"<td>{held_cell}</td>",
        ]
        rows_html.append("<tr>" + "".join(cells) + "</tr>")

    return (
        '<section><h2>Top candidates by FundScore</h2>'
        '<table class="data"><thead><tr>'
        + "".join(header_cells)
        + "</tr></thead><tbody>"
        + "".join(rows_html)
        + "</tbody></table></section>"
    )


def _render_fit_candidates(fit_candidates: pd.DataFrame) -> str:
    if fit_candidates is None or fit_candidates.empty:
        return ""

    headers = (
        ("#", "Fit_Rank"),
        ("Symbol", "Candidate_Symbol"),
        ("Name", "Name"),
        ("Total Drift After", "Total_Abs_Drift_After"),
        ("Δ Total", "Total_Abs_Drift_Change"),
        ("Max Drift After", "Max_Abs_Drift_After"),
        ("Stylebox After", "Stylebox_Drift_After"),
        ("Sector After", "Sector_Drift_After"),
        ("Fit Label", "Fit_Label"),
        ("Held?", None),
    )
    head = "".join(f"<th>{_esc(h)}</th>" for h, _ in headers)
    rows: List[str] = []
    for _, row in fit_candidates.iterrows():
        held_flag = bool(_safe_get(row, "Already_Held"))
        held_cell = "<span class=\"held\">held</span>" if held_flag else "—"
        cells = [
            f"<td>{_fmt_int(_safe_get(row, 'Fit_Rank'))}</td>",
            f"<td><code>{_esc(_safe_get(row, 'Candidate_Symbol'))}</code></td>",
            f"<td>{_esc(_safe_get(row, 'Name'))}</td>",
            f"<td>{_fmt_float(_safe_get(row, 'Total_Abs_Drift_After'), 3)}</td>",
            f"<td>{_fmt_float(_safe_get(row, 'Total_Abs_Drift_Change'), 3)}</td>",
            f"<td>{_fmt_float(_safe_get(row, 'Max_Abs_Drift_After'), 3)}</td>",
            f"<td>{_fmt_float(_safe_get(row, 'Stylebox_Drift_After'), 3)}</td>",
            f"<td>{_fmt_float(_safe_get(row, 'Sector_Drift_After'), 3)}</td>",
            f"<td>{_esc(_safe_get(row, 'Fit_Label'))}</td>",
            f"<td>{held_cell}</td>",
        ]
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<section><h2>Benchmark-fit candidates</h2>'
        '<p class="muted">Drift = current model − benchmark, summed across '
        'stylebox &amp; sector buckets. Lower is closer to the static '
        '100/0 equity benchmark.</p>'
        '<table class="data"><thead><tr>'
        + head
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></section>"
    )


def _render_headline_picks(summary: Mapping[str, Any]) -> str:
    if not summary.get("benchmark_fit_enabled"):
        return ""
    best_fund = summary.get("best_fundscore_candidate") or "—"
    best_fit = summary.get("best_benchmark_fit_candidate") or "—"
    balanced = summary.get("balanced_candidate") or "—"
    return (
        '<section class="picks"><h2>Headline picks</h2>'
        '<table class="kv">'
        f"<tr><th>Best by FundScore</th><td><code>{_esc(best_fund)}</code></td></tr>"
        f"<tr><th>Best by benchmark fit</th><td><code>{_esc(best_fit)}</code></td></tr>"
        f"<tr><th>Balanced (FundScore + fit)</th><td><code>{_esc(balanced)}</code></td></tr>"
        "</table></section>"
    )


def _render_drift_summary(
    summary: Mapping[str, Any],
    current_vs_benchmark: pd.DataFrame,
) -> str:
    if not summary.get("benchmark_fit_enabled"):
        return ""

    parts: List[str] = []
    parts.append(
        '<section><h2>Current vs benchmark drift</h2>'
        '<table class="kv">'
        "<tr><th>Baseline fit label</th>"
        f"<td>{_esc(summary.get('baseline_fit_label'))}</td></tr>"
        "<tr><th>Total abs drift</th>"
        f"<td>{_fmt_float(summary.get('baseline_total_abs_drift'), 3)}</td></tr>"
        "<tr><th>Max bucket</th>"
        f"<td><code>{_esc(summary.get('baseline_max_drift_bucket'))}</code> "
        f"@ {_fmt_float(summary.get('baseline_max_abs_drift'), 3)}</td></tr>"
        "</table>"
    )

    if current_vs_benchmark is not None and not current_vs_benchmark.empty:
        # Show top-N rows by absolute drift so the brief stays one-page-ish.
        df = current_vs_benchmark.copy()
        if "Active_Drift" in df.columns:
            df["_abs"] = df["Active_Drift"].abs()
            df = df.sort_values("_abs", ascending=False).drop(columns=["_abs"])
        df = df.head(10)
        head_cols = list(df.columns)
        head = "".join(f"<th>{_esc(c)}</th>" for c in head_cols)
        body_rows: List[str] = []
        for _, row in df.iterrows():
            tds: List[str] = []
            for c in head_cols:
                val = row[c]
                if isinstance(val, (int, float)) and not (
                    isinstance(val, float) and math.isnan(val)
                ):
                    tds.append(f"<td>{_fmt_float(val, 3)}</td>")
                else:
                    tds.append(f"<td>{_esc(val)}</td>")
            body_rows.append("<tr>" + "".join(tds) + "</tr>")
        parts.append(
            '<p class="muted">Top buckets by absolute drift '
            "(higher absolute value = greater divergence from benchmark):</p>"
            '<table class="data"><thead><tr>'
            + head
            + "</tr></thead><tbody>"
            + "".join(body_rows)
            + "</tbody></table>"
        )
    parts.append("</section>")
    return "".join(parts)


def _render_data_quality(summary: Mapping[str, Any]) -> str:
    items: List[str] = []
    items.append(
        "Universe row count: "
        f"<strong>{_esc(summary.get('universe_row_count', 0))}</strong> "
        "rows in the dual-score table for this run."
    )
    items.append(
        "Same-category pool size: "
        f"<strong>{_esc(summary.get('category_pool_size', 0))}</strong> "
        "before exclusions."
    )
    if summary.get("alias_applied"):
        items.append(
            "Share-class alias applied — committee-facing ticker resolved "
            "to a different scored symbol via the symbol-aliases table."
        )
    if summary.get("benchmark_fit_enabled"):
        missing_h = summary.get("missing_holdings_exposures") or []
        missing_b = summary.get("missing_benchmark_exposures") or []
        if missing_h:
            items.append(
                "Missing exposure rows for current holdings: "
                f"<code>{_esc(', '.join(missing_h))}</code>. "
                "Drift math treats them as zero-exposure — review before "
                "acting on the fit ranking."
            )
        if missing_b:
            items.append(
                "Missing exposure rows for benchmark constituents: "
                f"<code>{_esc(', '.join(missing_b))}</code>."
            )
    items.append(EPHEMERAL_STORAGE_NOTE)
    items.append(
        "This is a research short list, not an investment recommendation. "
        "Confirm current share-class availability, minimums, and operational "
        "fit before recommending to the committee."
    )
    return (
        '<section><h2>Data quality &amp; assumptions</h2><ul>'
        + "".join(f"<li>{i}</li>" for i in items)
        + "</ul></section>"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        "Helvetica Neue", Arial, sans-serif;
    color: #111;
    background: #fff;
    margin: 0;
    padding: 32px 48px;
    line-height: 1.45;
    font-size: 13px;
}
h1 { font-size: 22px; margin: 0 0 4px; }
h2 {
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid #ddd;
    padding-bottom: 4px;
    margin: 24px 0 10px;
}
header.brief-header { border-bottom: 2px solid #222; padding-bottom: 10px; }
.meta { color: #555; margin: 4px 0 0; font-size: 12px; }
.alias { color: #555; font-weight: normal; font-size: 14px; }
.universe-banner {
    margin: 8px 0 0;
    padding: 6px 10px;
    border-left: 4px solid #888;
    background: #f6f6f6;
    font-size: 12px;
}
.universe-banner.committee { border-left-color: #1f6f3f; background: #ecf6ee; }
.universe-banner.uploaded  { border-left-color: #1f4e8c; background: #eef3fa; }
.universe-banner.discovery { border-left-color: #b58000; background: #fff7e0; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
       font-size: 12px; background: #f4f4f4; padding: 1px 4px;
       border-radius: 3px; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 12px; }
table.kv th { text-align: left; width: 28%; padding: 4px 8px; vertical-align: top;
              background: #f8f8f8; font-weight: 600; }
table.kv td { padding: 4px 8px; vertical-align: top; }
table.data th, table.data td {
    border: 1px solid #ddd;
    padding: 4px 6px;
    text-align: left;
    vertical-align: top;
    font-size: 12px;
}
table.data th { background: #f0f0f0; font-weight: 600; }
table.data tr:nth-child(even) td { background: #fafafa; }
.muted { color: #666; font-size: 12px; }
.held { color: #a23; font-weight: 600; }
section.picks table.kv th { background: #fff7d6; }
ul { padding-left: 22px; margin: 6px 0 12px; }
li { margin-bottom: 4px; }
@media print {
    body { padding: 16px 24px; font-size: 11px; }
    h1 { font-size: 18px; }
    h2 { font-size: 12px; margin: 16px 0 6px; }
    section { page-break-inside: avoid; }
    .no-print { display: none !important; }
}
"""


def render_printable_brief_html(
    result_or_loaded: Any,
    *,
    run_date: Optional[str] = None,
) -> str:
    """Render a self-contained HTML printable brief.

    Accepts either:
        * a ``ReplacementResult`` dataclass (in-memory build), or
        * a dict from ``replacement_workbench.load_replacement`` (persisted).
    """
    d = _result_to_dict(result_or_loaded)
    summary = dict(d.get("summary") or {})
    if run_date and not summary.get("run_date"):
        summary["run_date"] = run_date

    ticker = (
        summary.get("ticker")
        or getattr(result_or_loaded, "ticker", None)
        or "—"
    )
    resolved = (
        summary.get("resolved_ticker")
        or getattr(result_or_loaded, "resolved_ticker", None)
        or ticker
    )
    alias_applied = bool(
        summary.get("alias_applied")
        or getattr(result_or_loaded, "alias_applied", False)
    )

    sections: List[str] = []
    sections.append(_render_header(summary, ticker, resolved, alias_applied))
    sections.append(
        _render_current_holding(
            d["current_profile"], summary, ticker, resolved, alias_applied,
        )
    )
    sections.append(_render_methodology(summary))
    sections.append(_render_candidates(d["candidates"]))
    sections.append(_render_headline_picks(summary))
    sections.append(_render_fit_candidates(d["benchmark_fit_candidates"]))
    sections.append(_render_drift_summary(summary, d["current_vs_benchmark"]))
    sections.append(_render_data_quality(summary))

    body = "".join(s for s in sections if s)
    title = f"Replacement Brief — {ticker}"
    return (
        "<!DOCTYPE html>\n<html lang=\"en\"><head>"
        f"<meta charset=\"utf-8\"><title>{_esc(title)}</title>"
        f"<style>{CSS}</style></head><body>"
        f"{body}"
        "</body></html>\n"
    )


def build_artifact_zip(
    loaded: Mapping[str, Any],
    *,
    html_brief: Optional[str] = None,
    zip_name: Optional[str] = None,  # accepted for parity; unused internally
) -> bytes:
    """Bundle every available workbench artifact into a single ZIP.

    ``loaded`` should be a dict matching the shape returned by
    ``replacement_workbench.load_replacement`` plus, optionally, a
    ``brief_markdown`` and ``summary``. We only include artifacts that have
    actual content — empty frames are skipped so the ZIP doesn't ship
    misleading 0-row CSVs.
    """
    del zip_name  # name belongs to the caller's download_button

    summary = loaded.get("summary") or {}
    ticker = summary.get("ticker") or "REPLACEMENT"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if html_brief:
            zf.writestr(f"{ticker}_printable_brief.html", html_brief)

        bm = loaded.get("brief_markdown") or ""
        if bm:
            zf.writestr(f"{ticker}_replacement_brief.md", bm)

        zf.writestr(
            f"{ticker}_replacement_summary.json",
            json.dumps(summary, indent=2, sort_keys=True, default=str),
        )

        df_files: Dict[str, str] = {
            "candidates": f"{ticker}_replacement_candidates.csv",
            "current_profile": f"{ticker}_current_holding_profile.csv",
            "benchmark_fit_candidates": f"{ticker}_benchmark_fit_candidates.csv",
            "current_vs_benchmark": f"{ticker}_current_vs_benchmark_exposure.csv",
            "replacement_delta": f"{ticker}_replacement_exposure_delta.csv",
        }
        for key, fname in df_files.items():
            df = loaded.get(key)
            if isinstance(df, pd.DataFrame) and not df.empty:
                zf.writestr(fname, df.to_csv(index=False))
    return buf.getvalue()
