"""
FundScore — Streamlit Fund Scoring App
=======================================
Multi-page analysis tool for portfolio managers.

Run:  streamlit run app.py
"""

import io
import os
from typing import Dict, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from scoring_engine import (
    CSV_COLUMNS,
    get_metric_percentiles,
    get_score_band,
    load_and_score,
    score_funds,
    SYSTEM_2023_METRICS,
    ACTIVE_METRICS,
    PASSIVE_METRICS,
)

# ---------------------------------------------------------------------------
# Page config — must be the very first Streamlit call
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="FundScore",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------

BADGE_CSS = """
<style>
/* Score badges */
.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 4px;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
.badge-STRONG { background: #1a4a3a; color: #4ade80; border: 1px solid #2d6a52; }
.badge-REVIEW { background: #3d3418; color: #fbbf24; border: 1px solid #5c4d1e; }
.badge-WEAK   { background: #4a1a1a; color: #f87171; border: 1px solid #6a2828; }

/* System mode badges */
.system-badge-2025 {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    background: #12283a;
    color: #4F98A3;
    border: 1px solid #1e4a6a;
    margin-bottom: 12px;
}
.system-badge-2023 {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    background: #281a00;
    color: #f59e0b;
    border: 1px solid #6a4200;
    margin-bottom: 12px;
}
.system-badge-compare {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    background: #1a1a3a;
    color: #a78bfa;
    border: 1px solid #3a2a6a;
    margin-bottom: 12px;
}

/* KPI cards */
.kpi-card {
    background: #1C1B19;
    border: 1px solid #2a2927;
    border-radius: 8px;
    padding: 18px 22px;
    margin-bottom: 8px;
}
.kpi-label {
    font-size: 0.72rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #7a7875;
    margin-bottom: 4px;
}
.kpi-value {
    font-size: 2rem;
    font-weight: 700;
    color: #CDCCCA;
    line-height: 1.1;
}
.kpi-sub {
    font-size: 0.75rem;
    color: #4F98A3;
    margin-top: 2px;
}

/* Score colour helpers */
.score-strong { color: #4ade80; font-weight: 700; }
.score-review { color: #fbbf24; font-weight: 700; }
.score-weak   { color: #f87171; font-weight: 700; }

/* Section header */
.section-header {
    font-size: 0.75rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #7a7875;
    border-bottom: 1px solid #2a2927;
    padding-bottom: 6px;
    margin-bottom: 16px;
}

/* Sidebar branding */
.sidebar-brand {
    font-size: 1.25rem;
    font-weight: 800;
    color: #4F98A3;
    letter-spacing: -0.01em;
    padding: 4px 0 16px 0;
}

/* Explainer cards */
.strength-card {
    background: #0d2e1a;
    border: 1px solid #2d6a52;
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 10px;
}
.weakness-card {
    background: #2e0d0d;
    border: 1px solid #6a2828;
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 10px;
}
.metric-name {
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    margin-bottom: 4px;
}
.metric-sentence {
    font-size: 0.85rem;
    color: #CDCCCA;
    line-height: 1.5;
}
.metric-stats {
    font-size: 0.72rem;
    color: #7a7875;
    margin-top: 4px;
}

/* Comparison cards */
.compare-card-2023 {
    background: #1e1500;
    border: 1px solid #5c4d1e;
    border-radius: 8px;
    padding: 18px 22px;
    margin-bottom: 8px;
}
.compare-card-2025 {
    background: #0a1e28;
    border: 1px solid #1e4a6a;
    border-radius: 8px;
    padding: 18px 22px;
    margin-bottom: 8px;
}
.compare-change-positive {
    color: #4ade80;
    font-weight: 700;
    font-size: 1.4rem;
}
.compare-change-negative {
    color: #f87171;
    font-weight: 700;
    font-size: 1.4rem;
}
</style>
"""

st.markdown(BADGE_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Plotly dark theme defaults
# ---------------------------------------------------------------------------

PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="#171614",
    plot_bgcolor="#1C1B19",
    font=dict(color="#CDCCCA", family="Inter, system-ui, sans-serif"),
    margin=dict(t=36, b=36, l=36, r=20),
)


def apply_theme(fig: go.Figure) -> go.Figure:
    fig.update_layout(**PLOTLY_LAYOUT)
    return fig


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

SAMPLE_PATH = os.path.join(os.path.dirname(__file__), "sample_data.csv")
SCORES_2023_PATH = os.path.join(os.path.dirname(__file__), "scores_2023.csv")


@st.cache_data(show_spinner="Scoring funds…")
def get_scored_data(path: str) -> pd.DataFrame:
    return load_and_score(path)


@st.cache_data(show_spinner="Loading 2023 scores…")
def load_2023_scores() -> pd.DataFrame:
    """Load pre-calculated 2023 scores from the legacy scoring system."""
    if os.path.exists(SCORES_2023_PATH):
        return pd.read_csv(SCORES_2023_PATH)
    return pd.DataFrame()


def get_data() -> pd.DataFrame:
    """Return 2025 scored DataFrame — either from uploaded file or sample data."""
    if "scored_df" in st.session_state and st.session_state["scored_df"] is not None:
        return st.session_state["scored_df"]
    if os.path.exists(SAMPLE_PATH):
        return get_scored_data(SAMPLE_PATH)
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

SCORE_COL = "Score_Final"
BAND_COL = "Score_Band"
TYPE_COL = "Fund_Type"
SYM_COL = CSV_COLUMNS["symbol"]
NAME_COL = CSV_COLUMNS["name"]
CAT_COL = CSV_COLUMNS["category"]


def badge_html(band: str) -> str:
    return f'<span class="badge badge-{band}">{band}</span>'


def score_color_class(score) -> str:
    if pd.isna(score):
        return "score-weak"
    if score >= 80:
        return "score-strong"
    if score >= 60:
        return "score-review"
    return "score-weak"


def fmt_score(score) -> str:
    return f"{score:.1f}" if not pd.isna(score) else "—"


def kpi_card(label: str, value: str, sub: str = "") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'{sub_html}</div>'
    )


def score_color_hex(score) -> str:
    if pd.isna(score):
        return "#f87171"
    if score >= 80:
        return "#4ade80"
    if score >= 60:
        return "#fbbf24"
    return "#f87171"


def style_score_col(val):
    """Styler function for score columns — 80/60 thresholds."""
    if pd.isna(val):
        return ""
    if val >= 80:
        return "color: #4ade80; font-weight: 700"
    if val >= 60:
        return "color: #fbbf24; font-weight: 700"
    return "color: #f87171; font-weight: 700"


def style_change_col(val):
    """Styler for score change column."""
    if pd.isna(val):
        return ""
    if val > 5:
        return "color: #4ade80; font-weight: 700"
    if val > 0:
        return "color: #86efac"
    if val < -5:
        return "color: #f87171; font-weight: 700"
    if val < 0:
        return "color: #fca5a5"
    return ""


# ---------------------------------------------------------------------------
# Sidebar Navigation
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown('<div class="sidebar-brand">⬡ FundScore</div>', unsafe_allow_html=True)

    # System selector
    scoring_system = st.selectbox(
        "Scoring System",
        ["2025 System (Current)", "2023 System (Legacy)", "2023 vs 2025 Comparison"],
        index=0,
        key="scoring_system",
    )

    st.markdown("---")

    page = st.radio(
        "Navigation",
        ["Dashboard", "Batch Scores", "Fund Lookup", "Category Analysis",
         "Score Explainer", "2023 vs 2025 Comparison", "PDF Reports", "History",
         "Monthly Workflow", "Upload CSV"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    df = get_data()
    df_2023 = load_2023_scores()
    if not df.empty:
        st.caption(f"**{len(df):,}** funds (2025)")
        n_passive = (df[TYPE_COL] == "Passive").sum()
        n_active = (df[TYPE_COL] == "Active").sum()
        st.caption(f"Passive: {n_passive:,}  ·  Active: {n_active:,}")
    if not df_2023.empty:
        st.caption(f"**{len(df_2023):,}** funds (2023)")
    st.markdown("---")
    st.caption("FundScore · Portfolio Analytics")


# ===========================================================================
# PAGE: Dashboard
# ===========================================================================

if page == "Dashboard":
    system = st.session_state.get("scoring_system", "2025 System (Current)")

    if system == "2023 System (Legacy)":
        st.markdown(
            '<span class="system-badge-2023">2023 SCORING SYSTEM (LEGACY)</span>',
            unsafe_allow_html=True,
        )
        st.markdown("## Dashboard")
        df_2023 = load_2023_scores()
        if df_2023.empty:
            st.warning("2023 scores file not found.")
            st.stop()

        scored = df_2023[df_2023["Score_2023"].notna()]
        total = len(df_2023)
        avg_score = scored["Score_2023"].mean()
        pct_strong = (scored["Score_2023"] >= 80).sum() / len(scored) * 100
        pct_weak = (scored["Score_2023"] < 60).sum() / len(scored) * 100

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(kpi_card("Total Funds (2023)", f"{total:,}"), unsafe_allow_html=True)
        with c2:
            st.markdown(kpi_card("Average Score", f"{avg_score:.1f}", "2023 Combined System"), unsafe_allow_html=True)
        with c3:
            st.markdown(kpi_card("Strong (≥80)", f"{pct_strong:.1f}%"), unsafe_allow_html=True)
        with c4:
            st.markdown(kpi_card("Weak (<60)", f"{pct_weak:.1f}%"), unsafe_allow_html=True)

        st.markdown("---")
        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown('<div class="section-header">Score Distribution (2023)</div>', unsafe_allow_html=True)
            fig_hist = px.histogram(
                scored, x="Score_2023", nbins=50,
                color_discrete_sequence=["#f59e0b"],
                labels={"Score_2023": "Score (2023 System)"},
            )
            fig_hist.add_vline(x=80, line_dash="dash", line_color="#4ade80", annotation_text="Strong", annotation_position="top right")
            fig_hist.add_vline(x=60, line_dash="dash", line_color="#f87171", annotation_text="Weak", annotation_position="top right")
            apply_theme(fig_hist)
            st.plotly_chart(fig_hist, use_container_width=True)

        with col_right:
            st.markdown('<div class="section-header">Category Average Scores (Top 20)</div>', unsafe_allow_html=True)
            cat_avg = (
                scored.groupby("Category Name")["Score_2023"]
                .agg(["mean", "count"])
                .reset_index()
                .rename(columns={"mean": "Avg Score", "count": "N"})
                .query("N >= 3")
                .sort_values("Avg Score", ascending=False)
                .head(20)
            )
            fig_bar = px.bar(
                cat_avg, x="Avg Score", y="Category Name",
                orientation="h",
                color="Avg Score",
                color_continuous_scale=["#f87171", "#fbbf24", "#4ade80"],
                range_color=[0, 100],
                text=cat_avg["Avg Score"].round(1),
                labels={"Category Name": ""},
            )
            fig_bar.update_traces(textposition="outside", textfont_size=10)
            fig_bar.update_coloraxes(showscale=False)
            apply_theme(fig_bar)
            fig_bar.update_layout(yaxis=dict(autorange="reversed"), height=520)
            st.plotly_chart(fig_bar, use_container_width=True)

    elif system == "2023 vs 2025 Comparison":
        st.markdown(
            '<span class="system-badge-compare">2023 VS 2025 COMPARISON MODE</span>',
            unsafe_allow_html=True,
        )
        st.markdown("## Dashboard — System Comparison")
        df_2023 = load_2023_scores()
        df_2025 = get_data()

        if df_2023.empty or df_2025.empty:
            st.warning("Both datasets are required for comparison.")
            st.stop()

        # Merge on symbol
        scored_2025 = df_2025[df_2025[SCORE_COL].notna()]
        merged = df_2023[["Symbol", "Score_2023"]].merge(
            scored_2025[[SYM_COL, SCORE_COL, TYPE_COL, CAT_COL, NAME_COL]].rename(columns={SYM_COL: "Symbol"}),
            on="Symbol",
            how="inner"
        )
        merged["Change"] = merged[SCORE_COL] - merged["Score_2023"]

        # KPI side-by-side
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(kpi_card("Shared Funds", f"{len(merged):,}", "in both datasets"), unsafe_allow_html=True)
        with c2:
            st.markdown(kpi_card("Avg Score 2023", f"{merged['Score_2023'].mean():.1f}"), unsafe_allow_html=True)
        with c3:
            st.markdown(kpi_card("Avg Score 2025", f"{merged[SCORE_COL].mean():.1f}"), unsafe_allow_html=True)
        with c4:
            avg_chg = merged["Change"].mean()
            color = "#4ade80" if avg_chg >= 0 else "#f87171"
            sign = "+" if avg_chg >= 0 else ""
            st.markdown(
                f'<div class="kpi-card"><div class="kpi-label">Avg Change</div>'
                f'<div class="kpi-value" style="color:{color}">{sign}{avg_chg:.1f}</div>'
                f'<div class="kpi-sub">2023 → 2025</div></div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")

        col_left, col_right = st.columns(2)
        with col_left:
            st.markdown('<div class="section-header">Score Distribution Comparison</div>', unsafe_allow_html=True)
            dist_data = pd.concat([
                pd.DataFrame({"Score": merged["Score_2023"], "System": "2023 Combined"}),
                pd.DataFrame({"Score": merged[SCORE_COL], "System": "2025 Current"}),
            ])
            fig_hist = px.histogram(
                dist_data, x="Score", color="System", nbins=40, barmode="overlay",
                opacity=0.7,
                color_discrete_map={"2023 Combined": "#f59e0b", "2025 Current": "#4F98A3"},
            )
            fig_hist.add_vline(x=80, line_dash="dash", line_color="#4ade80", annotation_text="Strong")
            fig_hist.add_vline(x=60, line_dash="dash", line_color="#f87171", annotation_text="Weak")
            apply_theme(fig_hist)
            st.plotly_chart(fig_hist, use_container_width=True)

        with col_right:
            st.markdown('<div class="section-header">Biggest Movers</div>', unsafe_allow_html=True)
            biggest_movers = merged.nlargest(10, "Change")[["Symbol", NAME_COL, "Score_2023", SCORE_COL, "Change"]]
            biggest_decliners = merged.nsmallest(10, "Change")[["Symbol", NAME_COL, "Score_2023", SCORE_COL, "Change"]]
            movers_all = pd.concat([biggest_movers, biggest_decliners]).rename(
                columns={"Score_2023": "2023 Score", SCORE_COL: "2025 Score", NAME_COL: "Name"}
            )
            movers_all["2023 Score"] = movers_all["2023 Score"].round(1)
            movers_all["2025 Score"] = movers_all["2025 Score"].round(1)
            movers_all["Change"] = movers_all["Change"].round(1)
            st.dataframe(
                movers_all.style.map(style_change_col, subset=["Change"]),
                use_container_width=True,
                hide_index=True,
                height=420,
            )

    else:
        # Default: 2025 System
        st.markdown(
            '<span class="system-badge-2025">2025 SCORING SYSTEM (CURRENT)</span>',
            unsafe_allow_html=True,
        )
        st.markdown("## Dashboard")
        df = get_data()

        if df.empty:
            st.warning("No data available. Upload a CSV on the **Upload CSV** page.")
            st.stop()

        scored = df[df[SCORE_COL].notna()]
        total = len(df)
        avg_score = scored[SCORE_COL].mean()
        pct_strong = (scored[BAND_COL] == "STRONG").sum() / len(scored) * 100
        pct_weak = (scored[BAND_COL] == "WEAK").sum() / len(scored) * 100

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(kpi_card("Total Funds", f"{total:,}"), unsafe_allow_html=True)
        with c2:
            st.markdown(kpi_card("Average Score", f"{avg_score:.1f}", "out of 100"), unsafe_allow_html=True)
        with c3:
            st.markdown(kpi_card("Strong (≥80)", f"{pct_strong:.1f}%"), unsafe_allow_html=True)
        with c4:
            st.markdown(kpi_card("Weak (<60)", f"{pct_weak:.1f}%"), unsafe_allow_html=True)

        st.markdown("---")

        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.markdown('<div class="section-header">Score Distribution</div>', unsafe_allow_html=True)
            fig_hist = px.histogram(
                scored,
                x=SCORE_COL,
                color=TYPE_COL,
                nbins=50,
                barmode="overlay",
                opacity=0.75,
                color_discrete_map={"Passive": "#4F98A3", "Active": "#8B6FC5"},
                labels={SCORE_COL: "Score", TYPE_COL: "Type"},
            )
            fig_hist.add_vline(x=80, line_dash="dash", line_color="#4ade80", annotation_text="Strong", annotation_position="top right")
            fig_hist.add_vline(x=60, line_dash="dash", line_color="#f87171", annotation_text="Weak", annotation_position="top right")
            apply_theme(fig_hist)
            st.plotly_chart(fig_hist, use_container_width=True)

        with col_right:
            st.markdown('<div class="section-header">Category Average Scores (Top 20)</div>', unsafe_allow_html=True)
            cat_avg = (
                scored.groupby(CAT_COL)[SCORE_COL]
                .agg(["mean", "count"])
                .reset_index()
                .rename(columns={"mean": "Avg Score", "count": "N"})
                .query("N >= 3")
                .sort_values("Avg Score", ascending=False)
                .head(20)
            )
            fig_bar = px.bar(
                cat_avg,
                x="Avg Score",
                y=CAT_COL,
                orientation="h",
                color="Avg Score",
                color_continuous_scale=["#f87171", "#fbbf24", "#4ade80"],
                range_color=[0, 100],
                text=cat_avg["Avg Score"].round(1),
                labels={CAT_COL: ""},
            )
            fig_bar.update_traces(textposition="outside", textfont_size=10)
            fig_bar.update_coloraxes(showscale=False)
            apply_theme(fig_bar)
            fig_bar.update_layout(yaxis=dict(autorange="reversed"), height=520)
            st.plotly_chart(fig_bar, use_container_width=True)

        # Band breakdown
        st.markdown('<div class="section-header">Score Band Breakdown</div>', unsafe_allow_html=True)
        band_counts = scored[BAND_COL].value_counts().reset_index()
        band_counts.columns = ["Band", "Count"]
        b1, b2, b3 = st.columns(3)
        for col_widget, band, color in zip([b1, b2, b3], ["STRONG", "REVIEW", "WEAK"], ["#4ade80", "#fbbf24", "#f87171"]):
            n = band_counts.loc[band_counts["Band"] == band, "Count"].values
            n_val = int(n[0]) if len(n) else 0
            with col_widget:
                st.markdown(
                    f'<div class="kpi-card"><div class="kpi-label">{band}</div>'
                    f'<div class="kpi-value" style="color:{color}">{n_val:,}</div>'
                    f'<div class="kpi-sub">{n_val / len(scored) * 100:.1f}% of funds</div></div>',
                    unsafe_allow_html=True,
                )

        st.markdown("---")

        # Generate PDF Report button
        st.markdown('<div class="section-header">Export</div>', unsafe_allow_html=True)
        if st.button("Generate Full PDF Report", type="primary"):
            with st.spinner("Generating PDF…"):
                from pdf_report import generate_report
                pdf_bytes = generate_report(scored, title="Fund Scoring Report")
            st.download_button(
                "⬇ Download PDF Report",
                data=pdf_bytes,
                file_name="fund_scoring_report.pdf",
                mime="application/pdf",
            )


# ===========================================================================
# PAGE: Batch Scores
# ===========================================================================

elif page == "Batch Scores":
    system = st.session_state.get("scoring_system", "2025 System (Current)")
    st.markdown("## Batch Scores")
    df = get_data()
    df_2023 = load_2023_scores()

    if df.empty:
        st.warning("No data available. Upload a CSV on the **Upload CSV** page.")
        st.stop()

    # Filters
    with st.expander("Filters", expanded=True):
        f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
        with f1:
            search = st.text_input("Search symbol or name", placeholder="e.g. SCHD or Vanguard")
        with f2:
            all_cats = sorted(df[CAT_COL].dropna().unique())
            sel_cats = st.multiselect("Category", all_cats)
        with f3:
            sel_types = st.multiselect("Fund Type", ["Passive", "Active"])
        with f4:
            score_min, score_max = st.slider("Score range", 0, 100, (0, 100))

    filtered = df.copy()
    if search:
        mask = (
            filtered[SYM_COL].str.contains(search, case=False, na=False)
            | filtered[NAME_COL].str.contains(search, case=False, na=False)
        )
        filtered = filtered[mask]
    if sel_cats:
        filtered = filtered[filtered[CAT_COL].isin(sel_cats)]
    if sel_types:
        filtered = filtered[filtered[TYPE_COL].isin(sel_types)]
    filtered = filtered[
        (filtered[SCORE_COL].isna()) | (
            (filtered[SCORE_COL] >= score_min) & (filtered[SCORE_COL] <= score_max)
        )
    ]

    st.caption(f"Showing **{len(filtered):,}** of {len(df):,} funds")

    # Display columns
    display_cols = [SYM_COL, NAME_COL, TYPE_COL, CAT_COL, SCORE_COL, BAND_COL]
    extra_cols = [
        CSV_COLUMNS["expense_ratio"],
        CSV_COLUMNS["aum"],
        CSV_COLUMNS["max_drawdown_5y"],
    ]
    show_cols = display_cols + [c for c in extra_cols if c in filtered.columns]
    table = filtered[show_cols].copy()

    # Add 2023 scores and change column when comparison data is available
    if not df_2023.empty:
        score_map_2023 = df_2023.set_index("Symbol")["Score_2023"].to_dict()
        table["Score_2023"] = table[SYM_COL].map(score_map_2023)
        table["Change"] = table[SCORE_COL] - table["Score_2023"]

    # Format
    if CSV_COLUMNS["expense_ratio"] in table.columns:
        table[CSV_COLUMNS["expense_ratio"]] = (table[CSV_COLUMNS["expense_ratio"]] * 100).round(3).astype(str) + "%"
    if CSV_COLUMNS["aum"] in table.columns:
        table[CSV_COLUMNS["aum"]] = table[CSV_COLUMNS["aum"]].apply(
            lambda x: f"${x/1e9:.2f}B" if pd.notna(x) and x >= 1e9 else (f"${x/1e6:.0f}M" if pd.notna(x) else "—")
        )
    if SCORE_COL in table.columns:
        table[SCORE_COL] = table[SCORE_COL].apply(lambda x: round(x, 1) if pd.notna(x) else None)
    if "Score_2023" in table.columns:
        table["Score_2023"] = table["Score_2023"].apply(lambda x: round(x, 1) if pd.notna(x) else None)
    if "Change" in table.columns:
        table["Change"] = table["Change"].apply(lambda x: round(x, 1) if pd.notna(x) else None)

    table = table.rename(columns={SCORE_COL: "Score 2025", BAND_COL: "Band"})

    # Sort by change if in comparison mode
    if system == "2023 vs 2025 Comparison" and "Change" in table.columns:
        table = table.sort_values("Change", ascending=True)

    # Style
    style_cols = ["Score 2025"]
    if "Score_2023" in table.columns:
        style_cols.append("Score_2023")

    styler = table.style.map(style_score_col, subset=["Score 2025"])
    if "Score_2023" in table.columns:
        styler = styler.map(style_score_col, subset=["Score_2023"])
    if "Change" in table.columns:
        styler = styler.map(style_change_col, subset=["Change"])

    st.dataframe(
        styler,
        use_container_width=True,
        height=520,
    )

    # CSV export
    csv_bytes = table.to_csv(index=False).encode()
    st.download_button(
        "⬇ Download as CSV",
        data=csv_bytes,
        file_name="fund_scores_filtered.csv",
        mime="text/csv",
    )


# ===========================================================================
# PAGE: Fund Lookup
# ===========================================================================

elif page == "Fund Lookup":
    st.markdown("## Fund Lookup")
    df = get_data()
    df_2023 = load_2023_scores()

    if df.empty:
        st.warning("No data available. Upload a CSV on the **Upload CSV** page.")
        st.stop()

    ticker_input = st.text_input("Enter ticker symbol", placeholder="e.g. SCHD", max_chars=10)

    if not ticker_input:
        st.info("Enter a ticker symbol above to look up a fund.")
        st.stop()

    symbol = ticker_input.strip().upper()
    match = df[df[SYM_COL] == symbol]
    match_2023 = df_2023[df_2023["Symbol"] == symbol] if not df_2023.empty else pd.DataFrame()

    if match.empty and match_2023.empty:
        st.error(f"No fund found for ticker **{symbol}** in either dataset.")
        st.stop()

    # Determine what data we have
    has_2025 = not match.empty
    has_2023 = not match_2023.empty

    score_2025 = match.iloc[0].get(SCORE_COL) if has_2025 else None
    score_2023 = float(match_2023.iloc[0]["Score_2023"]) if has_2023 else None
    band_2025 = match.iloc[0].get(BAND_COL, "WEAK") if has_2025 else None
    fund_type = match.iloc[0].get(TYPE_COL, "Unknown") if has_2025 else "Unknown"
    cat = match.iloc[0].get(CAT_COL, "—") if has_2025 else match_2023.iloc[0].get("Category Name", "—")
    name = match.iloc[0].get(NAME_COL, symbol) if has_2025 else match_2023.iloc[0].get("Name", symbol)

    color_map = {"STRONG": "#4ade80", "REVIEW": "#fbbf24", "WEAK": "#f87171"}

    # --- Dual-score header ---
    if has_2025 and has_2023:
        delta = score_2025 - score_2023
        delta_sign = "+" if delta >= 0 else ""
        delta_color = "#4ade80" if delta >= 0 else "#f87171"
        score_color_val = color_map.get(band_2025, "#CDCCCA")

        st.markdown(
            f"""
            <div style="background:#1C1B19; border:1px solid #2a2927; border-radius:10px;
                        padding:28px 32px; margin-bottom:24px;">
                <div style="font-size:1.4rem; font-weight:700; color:#CDCCCA; margin-bottom:6px;">
                    {name}
                </div>
                <div style="font-size:0.9rem; color:#7a7875; margin-bottom:20px;">
                    {symbol} &nbsp;·&nbsp; {fund_type} &nbsp;·&nbsp; {cat}
                </div>
                <div style="display:flex; align-items:center; gap:40px; flex-wrap:wrap;">
                    <div style="text-align:center;">
                        <div style="font-size:0.7rem; letter-spacing:0.1em; text-transform:uppercase;
                                    color:#f59e0b; margin-bottom:4px;">2023 Score</div>
                        <div style="font-size:3rem; font-weight:800; color:#f59e0b; line-height:1;">
                            {score_2023:.1f}
                        </div>
                        <div style="font-size:0.7rem; color:#7a7875; margin-top:4px;">Combined System</div>
                    </div>
                    <div style="font-size:2rem; color:#4a4845;">→</div>
                    <div style="text-align:center;">
                        <div style="font-size:0.7rem; letter-spacing:0.1em; text-transform:uppercase;
                                    color:#4F98A3; margin-bottom:4px;">2025 Score</div>
                        <div style="font-size:3rem; font-weight:800; color:{score_color_val}; line-height:1;">
                            {fmt_score(score_2025)}
                        </div>
                        <div style="margin-top:4px;">{badge_html(band_2025)}</div>
                    </div>
                    <div style="text-align:center;">
                        <div style="font-size:0.7rem; letter-spacing:0.1em; text-transform:uppercase;
                                    color:#7a7875; margin-bottom:4px;">Change</div>
                        <div style="font-size:3rem; font-weight:800; color:{delta_color}; line-height:1;">
                            {delta_sign}{delta:.1f}
                        </div>
                        <div style="font-size:0.7rem; color:#7a7875; margin-top:4px;">pts vs 2023</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif has_2025:
        row = match.iloc[0]
        score = score_2025
        band = band_2025
        score_color = color_map.get(band, "#CDCCCA")
        st.markdown(
            f"""
            <div style="background:#1C1B19; border:1px solid #2a2927; border-radius:10px;
                        padding:28px 32px; margin-bottom:24px; display:flex; align-items:center; gap:40px;">
                <div>
                    <div style="font-size:0.72rem; letter-spacing:0.1em; text-transform:uppercase;
                                color:#7a7875; margin-bottom:4px;">Score (2025)</div>
                    <div style="font-size:4rem; font-weight:800; color:{score_color}; line-height:1;">
                        {fmt_score(score)}
                    </div>
                    <div style="margin-top:8px;">{badge_html(band)}</div>
                </div>
                <div>
                    <div style="font-size:1.4rem; font-weight:700; color:#CDCCCA;">{name}</div>
                    <div style="font-size:1rem; color:#7a7875; margin-top:4px;">{symbol}</div>
                    <div style="margin-top:10px; font-size:0.85rem; color:#9a9895;">
                        <span style="margin-right:18px;">Type: <strong>{fund_type}</strong></span>
                        <span>Category: <strong>{cat}</strong></span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        # 2023 only
        st.markdown(
            f"""
            <div style="background:#1C1B19; border:1px solid #2a2927; border-radius:10px;
                        padding:28px 32px; margin-bottom:24px;">
                <div style="font-size:1.4rem; font-weight:700; color:#CDCCCA; margin-bottom:6px;">{name}</div>
                <div style="font-size:0.9rem; color:#7a7875;">
                    {symbol} · {cat} · 2023 Score: <strong style="color:#f59e0b;">{score_2023:.1f}</strong>
                </div>
                <div style="margin-top:8px; font-size:0.8rem; color:#7a7875;">
                    Not found in the 2025 dataset.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Metrics and radar chart
    if has_2025:
        row = match.iloc[0]
        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.markdown('<div class="section-header">Key Metrics (2025 Data)</div>', unsafe_allow_html=True)

            metric_labels = {
                CSV_COLUMNS["expense_ratio"]: "Expense Ratio",
                CSV_COLUMNS["aum"]: "AUM",
                CSV_COLUMNS["max_drawdown_5y"]: "Max Drawdown (5Y)",
                CSV_COLUMNS["max_drawdown_10y"]: "Max Drawdown (10Y)",
                CSV_COLUMNS["downside_5y"]: "Downside Capture (5Y)",
                CSV_COLUMNS["downside_10y"]: "Downside Capture (10Y)",
                CSV_COLUMNS["returns_3y"]: "3Y Total Return",
                CSV_COLUMNS["returns_5y"]: "5Y Total Return",
                CSV_COLUMNS["returns_10y"]: "10Y Total Return",
            }

            rows = []
            for col, label in metric_labels.items():
                if col not in df.columns:
                    continue
                val = row.get(col)
                if pd.isna(val):
                    display_val = "—"
                elif "Return" in label:
                    display_val = f"{val * 100:.2f}%"
                elif "Expense" in label:
                    display_val = f"{val * 100:.3f}%"
                elif "AUM" in label:
                    if val >= 1e9:
                        display_val = f"${val / 1e9:.2f}B"
                    else:
                        display_val = f"${val / 1e6:.0f}M"
                elif "Drawdown" in label or "Downside" in label:
                    display_val = f"{val:.4f}"
                else:
                    display_val = f"{val:.4f}"
                rows.append({"Metric": label, "Value": display_val})

            # Add 2023-specific metrics if available
            if has_2023:
                r23 = match_2023.iloc[0]
                for col_23, label_23 in [
                    ("Alpha (vs Category) (5Y)", "Alpha (5Y)"),
                    ("Alpha (vs Category) (10Y)", "Alpha (10Y)"),
                    ("Median Manager Tenure", "Median Manager Tenure (yrs)"),
                    ("Average Manager Tenure", "Average Manager Tenure (yrs)"),
                ]:
                    val = r23.get(col_23)
                    if pd.notna(val):
                        rows.append({"Metric": f"{label_23} [2023 only]", "Value": f"{val:.2f}"})

            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )

        with col_right:
            st.markdown('<div class="section-header">Component Percentiles vs Category Peers</div>', unsafe_allow_html=True)

            pct_data = get_metric_percentiles(df, symbol)

            if pct_data:
                labels = list(pct_data.keys())
                values = list(pct_data.values())
                short_labels = [
                    l.replace(" (vs Category)", "")
                     .replace("Historical ", "")
                     .replace("Share Class Assets Under Management", "AUM")
                     .replace("Net Expense Ratio", "Expense Ratio")
                    for l in labels
                ]

                fig_radar = go.Figure()
                fig_radar.add_trace(
                    go.Scatterpolar(
                        r=values + [values[0]],
                        theta=short_labels + [short_labels[0]],
                        fill="toself",
                        fillcolor="rgba(79,152,163,0.25)",
                        line=dict(color="#4F98A3", width=2),
                        name=f"{symbol} (2025)",
                    )
                )
                fig_radar.update_layout(
                    polar=dict(
                        radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=9)),
                        angularaxis=dict(tickfont=dict(size=10)),
                        bgcolor="#1C1B19",
                    ),
                    showlegend=False,
                    **PLOTLY_LAYOUT,
                )
                st.plotly_chart(fig_radar, use_container_width=True)
            else:
                st.info("No percentile data available for this fund.")

        # Category rank context
        st.markdown('<div class="section-header">Category Rank (2025)</div>', unsafe_allow_html=True)
        cat_peers = df[df[CAT_COL] == cat][SCORE_COL].dropna()
        if len(cat_peers) > 0 and score_2025 is not None and pd.notna(score_2025):
            rank = (cat_peers < score_2025).sum() + 1
            total_cat = len(cat_peers)
            pct_rank = (cat_peers <= score_2025).sum() / total_cat * 100
            rc1, rc2, rc3 = st.columns(3)
            with rc1:
                st.metric("Rank in Category", f"#{rank} of {total_cat}")
            with rc2:
                st.metric("Category Percentile", f"{pct_rank:.0f}th")
            with rc3:
                st.metric("Category Avg Score", f"{cat_peers.mean():.1f}")

    # Cross-system comparison section (always shown if both datasets have data)
    if has_2025 and has_2023:
        st.markdown("---")
        with st.expander("📊 2023 vs 2025 System Analysis", expanded=True):
            from score_explainer import explain_score_difference

            with st.spinner("Generating cross-system analysis…"):
                diff = explain_score_difference(df_2023, df, symbol)

            if "error" in diff:
                st.warning(diff["error"])
            else:
                # Header
                delta = diff.get("delta")
                delta_color = "#4ade80" if (delta or 0) >= 0 else "#f87171"
                delta_sign = "+" if (delta or 0) >= 0 else ""

                st.markdown(
                    f'<div style="background:#1C1B19; border:1px solid #2a2927; border-radius:8px; '
                    f'padding:16px 20px; font-size:1rem; color:#CDCCCA; line-height:1.6;">'
                    f'{diff["header"]}</div>',
                    unsafe_allow_html=True,
                )

                st.markdown("")
                st.markdown("**Methodology Change**")
                st.markdown(
                    f'<div style="background:#12161f; border-left:3px solid #4F98A3; '
                    f'padding:12px 18px; font-size:0.88rem; color:#9a9895; margin-bottom:12px;">'
                    f'{diff["methodology_note"]}</div>',
                    unsafe_allow_html=True,
                )

                # 2023-only metrics
                if diff.get("metrics_2023_only"):
                    st.markdown("**Metrics Removed in 2025** (existed in 2023, not in 2025):")
                    for m in diff["metrics_2023_only"]:
                        contrib = m.get("contribution_2023", 0)
                        st.markdown(
                            f'<div class="weakness-card">'
                            f'<div class="metric-name" style="color:#f59e0b;">{m["metric"]}</div>'
                            f'<div class="metric-sentence">{m["note"]}</div>'
                            f'<div class="metric-stats">'
                            f'Weight in 2023: {m["weight_2023"]}% &nbsp;·&nbsp; '
                            f'Contribution in 2023: ~{contrib:.1f} pts &nbsp;·&nbsp; '
                            f'Weight in 2025: Not used'
                            f'</div></div>',
                            unsafe_allow_html=True,
                        )

                # 2025-only metrics
                if diff.get("metrics_2025_only"):
                    st.markdown("**Metrics Added in 2025** (not in 2023):")
                    for m in diff["metrics_2025_only"]:
                        contrib = m.get("contribution_2025", 0)
                        st.markdown(
                            f'<div class="strength-card">'
                            f'<div class="metric-name" style="color:#4F98A3;">{m["metric"]}</div>'
                            f'<div class="metric-sentence">{m["note"]}</div>'
                            f'<div class="metric-stats">'
                            f'Weight in 2025: {m["weight_2025"]}% &nbsp;·&nbsp; '
                            f'Contribution in 2025: ~{contrib:.1f} pts &nbsp;·&nbsp; '
                            f'Weight in 2023: Not used'
                            f'</div></div>',
                            unsafe_allow_html=True,
                        )

                # Net narrative
                if diff.get("net_narrative"):
                    st.markdown("**Net Analysis**")
                    st.markdown(
                        f'<div style="background:#1C1B19; border:1px solid #2a2927; border-radius:8px; '
                        f'padding:16px 20px; font-size:0.9rem; color:#CDCCCA; line-height:1.8; '
                        f'white-space:pre-line;">'
                        f'{diff["net_narrative"]}</div>',
                        unsafe_allow_html=True,
                    )

                # Shared metrics table
                if diff.get("shared_metrics"):
                    st.markdown("**Shared Metrics — Percentile Comparison**")
                    sm_df = pd.DataFrame(diff["shared_metrics"])
                    sm_df.columns = ["Metric", "Value (2023)", "Value (2025)", "Percentile (2023)", "Percentile (2025)"]
                    st.dataframe(sm_df, use_container_width=True, hide_index=True)

    # 2025 explain section
    if has_2025:
        st.markdown("---")
        with st.expander("🔍 Explain 2025 Score", expanded=False):
            from score_explainer import explain_score

            with st.spinner("Generating explanation…"):
                explanation = explain_score(df, symbol)

            if "error" in explanation:
                st.error(explanation["error"])
            else:
                st.markdown(f"**{explanation['summary']}**")
                st.caption(explanation["fund_type_note"])

                cov = explanation["data_coverage"]
                missing_str = ", ".join(cov["missing"]) if cov["missing"] else "none"
                st.caption(
                    f"Data coverage: {cov['pct']:.0f}% "
                    f"({cov['metrics_with_data']}/{cov['total_metrics']} metrics). "
                    f"Missing: {missing_str}."
                )

                s_col, w_col = st.columns(2)
                with s_col:
                    st.markdown("##### Top Contributors")
                    for s in explanation["strengths"]:
                        st.markdown(
                            f'<div class="strength-card">'
                            f'<div class="metric-name" style="color:#4ade80;">{s["metric"]}</div>'
                            f'<div class="metric-sentence">{s["sentence"]}</div>'
                            f'<div class="metric-stats">'
                            f'{s["percentile"]:.0f}th percentile · weight {s["weight"]} · +{s["contribution_points"]:.1f} pts'
                            f'</div></div>',
                            unsafe_allow_html=True,
                        )

                with w_col:
                    st.markdown("##### Bottom Contributors")
                    for w in explanation["weaknesses"]:
                        st.markdown(
                            f'<div class="weakness-card">'
                            f'<div class="metric-name" style="color:#f87171;">{w["metric"]}</div>'
                            f'<div class="metric-sentence">{w["sentence"]}</div>'
                            f'<div class="metric-stats">'
                            f'{w["percentile"]:.0f}th percentile · weight {w["weight"]} · {w["contribution_points"]:.1f} pts'
                            f'</div></div>',
                            unsafe_allow_html=True,
                        )


# ===========================================================================
# PAGE: Category Analysis
# ===========================================================================

elif page == "Category Analysis":
    st.markdown("## Category Analysis")
    df = get_data()

    if df.empty:
        st.warning("No data available. Upload a CSV on the **Upload CSV** page.")
        st.stop()

    all_cats = sorted(df[CAT_COL].dropna().unique())
    selected_cat = st.selectbox("Select a category", all_cats)

    cat_df = df[df[CAT_COL] == selected_cat].copy()
    scored_cat = cat_df[cat_df[SCORE_COL].notna()]

    # Summary metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card("Funds", str(len(cat_df))), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("Avg Score", f"{scored_cat[SCORE_COL].mean():.1f}" if len(scored_cat) else "—"), unsafe_allow_html=True)
    with c3:
        n_passive = (cat_df[TYPE_COL] == "Passive").sum()
        st.markdown(kpi_card("Passive", str(n_passive)), unsafe_allow_html=True)
    with c4:
        n_active = (cat_df[TYPE_COL] == "Active").sum()
        st.markdown(kpi_card("Active", str(n_active)), unsafe_allow_html=True)

    st.markdown("---")

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown('<div class="section-header">Score Distribution</div>', unsafe_allow_html=True)
        fig_hist = px.histogram(
            scored_cat,
            x=SCORE_COL,
            color=TYPE_COL,
            nbins=30,
            barmode="overlay",
            opacity=0.75,
            color_discrete_map={"Passive": "#4F98A3", "Active": "#8B6FC5"},
            labels={SCORE_COL: "Score"},
        )
        fig_hist.add_vline(x=80, line_dash="dash", line_color="#4ade80")
        fig_hist.add_vline(x=60, line_dash="dash", line_color="#f87171")
        apply_theme(fig_hist)
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_right:
        st.markdown('<div class="section-header">Score vs Expense Ratio</div>', unsafe_allow_html=True)
        exp_col = CSV_COLUMNS["expense_ratio"]
        if exp_col in scored_cat.columns:
            scatter_df = scored_cat[[SYM_COL, NAME_COL, SCORE_COL, TYPE_COL, exp_col]].dropna()
            scatter_df["ER%"] = scatter_df[exp_col] * 100
            fig_sc = px.scatter(
                scatter_df,
                x="ER%",
                y=SCORE_COL,
                color=TYPE_COL,
                hover_data={SYM_COL: True, NAME_COL: True, "ER%": ":.3f", SCORE_COL: ":.1f", TYPE_COL: False},
                color_discrete_map={"Passive": "#4F98A3", "Active": "#8B6FC5"},
                labels={"ER%": "Expense Ratio (%)", SCORE_COL: "Score"},
            )
            apply_theme(fig_sc)
            st.plotly_chart(fig_sc, use_container_width=True)

    # Ranked list
    st.markdown('<div class="section-header">Ranked Funds</div>', unsafe_allow_html=True)
    ranked = (
        scored_cat[[SYM_COL, NAME_COL, TYPE_COL, SCORE_COL, BAND_COL, CSV_COLUMNS["expense_ratio"]]]
        .sort_values(SCORE_COL, ascending=False)
        .reset_index(drop=True)
    )
    ranked.index += 1
    ranked = ranked.rename(columns={SCORE_COL: "Score", BAND_COL: "Band"})
    if CSV_COLUMNS["expense_ratio"] in ranked.columns:
        ranked[CSV_COLUMNS["expense_ratio"]] = (ranked[CSV_COLUMNS["expense_ratio"]] * 100).round(3).astype(str) + "%"

    def style_band(val):
        colors = {"STRONG": "color: #4ade80", "REVIEW": "color: #fbbf24", "WEAK": "color: #f87171"}
        return colors.get(str(val), "")

    st.dataframe(
        ranked.style
              .map(lambda v: "color: #4ade80; font-weight:700" if isinstance(v, (int, float)) and v >= 80 else
                                  ("color: #fbbf24; font-weight:700" if isinstance(v, (int, float)) and v >= 60 else
                                   ("color: #f87171" if isinstance(v, (int, float)) else "")), subset=["Score"])
              .map(style_band, subset=["Band"]),
        use_container_width=True,
        height=480,
    )


# ===========================================================================
# PAGE: Score Explainer
# ===========================================================================

elif page == "Score Explainer":
    from score_explainer import explain_score, explain_score_difference, generate_category_narrative

    st.markdown("## Score Explainer")
    st.markdown("Generate a human-readable narrative explaining why a fund scores the way it does.")

    df = get_data()
    df_2023 = load_2023_scores()
    if df.empty:
        st.warning("No data available. Upload a CSV on the **Upload CSV** page.")
        st.stop()

    ticker_input = st.text_input("Enter ticker symbol to explain", placeholder="e.g. SCHD", max_chars=10)

    if not ticker_input:
        st.info("Enter a ticker symbol above to generate a score explanation.")
        st.stop()

    symbol = ticker_input.strip().upper()

    with st.spinner(f"Analyzing {symbol}…"):
        explanation = explain_score(df, symbol)

    if "error" in explanation:
        st.error(explanation["error"])
        st.stop()

    score = explanation["score"]
    band = explanation["band"]
    color_map = {"STRONG": "#4ade80", "REVIEW": "#fbbf24", "WEAK": "#f87171"}
    score_color = color_map.get(band, "#CDCCCA")

    # Check 2023
    has_2023 = not df_2023.empty and (df_2023["Symbol"] == symbol).any()
    score_2023 = float(df_2023[df_2023["Symbol"] == symbol].iloc[0]["Score_2023"]) if has_2023 else None

    # Fund header
    if has_2023 and score_2023 is not None:
        delta = score - score_2023
        delta_sign = "+" if delta >= 0 else ""
        delta_color = "#4ade80" if delta >= 0 else "#f87171"
        st.markdown(
            f"""
            <div style="background:#1C1B19; border:1px solid #2a2927; border-radius:10px;
                        padding:22px 28px; margin-bottom:20px;">
                <div style="display:flex; align-items:center; gap:32px; flex-wrap:wrap;">
                    <div style="text-align:center;">
                        <div style="font-size:0.7rem; color:#f59e0b; text-transform:uppercase; letter-spacing:0.08em;">2023</div>
                        <div style="font-size:2.8rem; font-weight:800; color:#f59e0b; line-height:1;">{score_2023:.1f}</div>
                    </div>
                    <div style="font-size:1.5rem; color:#4a4845;">→</div>
                    <div style="text-align:center;">
                        <div style="font-size:0.7rem; color:#4F98A3; text-transform:uppercase; letter-spacing:0.08em;">2025</div>
                        <div style="font-size:2.8rem; font-weight:800; color:{score_color}; line-height:1;">{fmt_score(score)}</div>
                    </div>
                    <div style="text-align:center;">
                        <div style="font-size:0.7rem; color:#7a7875; text-transform:uppercase; letter-spacing:0.08em;">Change</div>
                        <div style="font-size:2.8rem; font-weight:800; color:{delta_color}; line-height:1;">{delta_sign}{delta:.1f}</div>
                    </div>
                    <div>
                        <div style="font-size:1.3rem; font-weight:700; color:#CDCCCA;">{explanation['name']} ({symbol})</div>
                        <div style="font-size:0.9rem; color:#7a7875; margin-top:4px;">{explanation['fund_type']} · {explanation['category']}</div>
                        <div style="margin-top:8px;">{badge_html(band)}</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div style="background:#1C1B19; border:1px solid #2a2927; border-radius:10px;
                        padding:22px 28px; margin-bottom:20px;">
                <div style="display:flex; align-items:center; gap:32px;">
                    <div style="font-size:3.5rem; font-weight:800; color:{score_color}; line-height:1;">
                        {fmt_score(score)}
                    </div>
                    <div>
                        <div style="font-size:1.3rem; font-weight:700; color:#CDCCCA;">
                            {explanation['name']} ({symbol})
                        </div>
                        <div style="font-size:0.9rem; color:#7a7875; margin-top:4px;">
                            {explanation['fund_type']} · {explanation['category']}
                        </div>
                        <div style="margin-top:8px;">{badge_html(band)}</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Summary narrative
    st.markdown("### 2025 Score Narrative")
    st.markdown(
        f'<div style="background:#1C1B19; border:1px solid #2a2927; border-radius:8px; '
        f'padding:18px 22px; font-size:1.05rem; line-height:1.7; color:#CDCCCA;">'
        f'{explanation["summary"]}</div>',
        unsafe_allow_html=True,
    )
    st.markdown("")
    st.markdown(
        f'<div style="background:#12161f; border-left:3px solid #4F98A3; '
        f'padding:12px 18px; font-size:0.88rem; color:#9a9895; margin-bottom:12px;">'
        f'{explanation["fund_type_note"]}</div>',
        unsafe_allow_html=True,
    )

    cov = explanation["data_coverage"]
    missing_str = ", ".join(cov["missing"]) if cov["missing"] else "none"
    st.caption(
        f"Data coverage: {cov['pct']:.0f}% "
        f"({cov['metrics_with_data']}/{cov['total_metrics']} metrics). "
        f"Missing: {missing_str}."
    )

    st.markdown("---")

    # Strengths & Weaknesses
    s_col, w_col = st.columns(2)

    with s_col:
        st.markdown("### Top Contributors")
        for s in explanation["strengths"]:
            st.markdown(
                f'<div class="strength-card">'
                f'<div class="metric-name" style="color:#4ade80;">{s["metric"]}</div>'
                f'<div class="metric-sentence">{s["sentence"]}</div>'
                f'<div class="metric-stats">'
                f'{s["percentile"]:.0f}th percentile &nbsp;·&nbsp; weight {s["weight"]} '
                f'&nbsp;·&nbsp; +{s["contribution_points"]:.1f} pts'
                f'</div></div>',
                unsafe_allow_html=True,
            )

    with w_col:
        st.markdown("### Bottom Contributors")
        for w in explanation["weaknesses"]:
            st.markdown(
                f'<div class="weakness-card">'
                f'<div class="metric-name" style="color:#f87171;">{w["metric"]}</div>'
                f'<div class="metric-sentence">{w["sentence"]}</div>'
                f'<div class="metric-stats">'
                f'{w["percentile"]:.0f}th percentile &nbsp;·&nbsp; weight {w["weight"]} '
                f'&nbsp;·&nbsp; {w["contribution_points"]:.1f} pts'
                f'</div></div>',
                unsafe_allow_html=True,
            )

    # Full component breakdown table
    st.markdown("---")
    st.markdown("### Full Component Breakdown (2025)")
    breakdown = explanation.get("breakdown", {})
    if breakdown:
        rows = []
        for key, info in sorted(breakdown.items(), key=lambda x: x[1]["contribution"], reverse=True):
            from score_explainer import METRIC_LABELS
            raw = info["raw_value"]
            if key == "expense_ratio":
                raw_str = f"{raw*100:.3f}%" if pd.notna(raw) else "—"
            elif key in ("returns_3y", "returns_5y", "returns_10y"):
                raw_str = f"{raw*100:.2f}%" if pd.notna(raw) else "—"
            elif key == "aum":
                if pd.notna(raw):
                    raw_str = f"${raw/1e9:.2f}B" if raw >= 1e9 else f"${raw/1e6:.0f}M"
                else:
                    raw_str = "—"
            else:
                raw_str = f"{raw:.4f}" if pd.notna(raw) else "—"
            rows.append({
                "Metric": METRIC_LABELS.get(key, key),
                "Raw Value": raw_str,
                "Percentile": f"{info['percentile']:.0f}th",
                "Weight": info["weight"],
                "Contribution (pts)": round(info["contribution"], 2),
            })
        breakdown_df = pd.DataFrame(rows)
        st.dataframe(breakdown_df, use_container_width=True, hide_index=True)

    # --- 2023 vs 2025 Analysis Section ---
    if has_2023:
        st.markdown("---")
        st.markdown("### 2023 vs 2025 Analysis")
        with st.spinner("Running cross-system comparison…"):
            diff = explain_score_difference(df_2023, df, symbol)

        if "error" in diff:
            st.warning(diff["error"])
        else:
            st.markdown(
                f'<div style="background:#1C1B19; border:1px solid #2a2927; border-radius:8px; '
                f'padding:16px 20px; font-size:1rem; color:#CDCCCA; line-height:1.6;">'
                f'{diff["header"]}</div>',
                unsafe_allow_html=True,
            )
            st.markdown("")
            st.markdown("**Methodology Difference**")
            st.info(diff["methodology_note"])

            if diff.get("metrics_2023_only"):
                st.markdown("**2023-Only Metrics (removed in 2025):**")
                for m in diff["metrics_2023_only"]:
                    st.markdown(f"- **{m['metric']}** (weight: {m['weight_2023']}% → 0%): {m['note']}")

            if diff.get("metrics_2025_only"):
                st.markdown("**2025-Only Metrics (added in 2025):**")
                for m in diff["metrics_2025_only"]:
                    st.markdown(f"- **{m['metric']}** (weight: 0% → {m['weight_2025']}%): {m['note']}")

            if diff.get("expense_note"):
                st.markdown(f"**Expense Ratio Reweighting:** {diff['expense_note']}")

            if diff.get("net_narrative"):
                st.markdown("**Net Analysis:**")
                st.markdown(
                    f'<div style="background:#1C1B19; border:1px solid #2a2927; border-radius:8px; '
                    f'padding:16px 20px; font-size:0.9rem; color:#CDCCCA; line-height:1.8; '
                    f'white-space:pre-line;">'
                    f'{diff["net_narrative"]}</div>',
                    unsafe_allow_html=True,
                )

            if diff.get("shared_metrics"):
                st.markdown("**Shared Metrics — Percentile Comparison:**")
                sm_df = pd.DataFrame(diff["shared_metrics"])
                sm_df.columns = ["Metric", "Value (2023)", "Value (2025)", "Percentile (2023)", "Percentile (2025)"]
                st.dataframe(sm_df, use_container_width=True, hide_index=True)

    # Cross-period comparison (legacy manual upload)
    with st.expander("Load a custom comparison dataset (optional)", expanded=False):
        st.markdown(
            "Upload a second scored CSV (e.g. a prior year export) to compare scores "
            "across different time periods or scoring system versions."
        )
        uploaded_compare = st.file_uploader("Comparison CSV", type=["csv"], key="compare_csv")
        if uploaded_compare is not None:
            try:
                raw_compare = pd.read_csv(uploaded_compare)
                df_compare = score_funds(raw_compare)
                st.success(f"Comparison dataset loaded: {len(df_compare):,} funds")
                diff2 = explain_score_difference(df_compare, df, symbol)
                if "error" in diff2:
                    st.warning(diff2["error"])
                else:
                    st.markdown(f"**{diff2['summary']}**")
                    st.info(diff2["system_change_note"])
            except Exception as e:
                st.error(f"Error loading comparison CSV: {e}")


# ===========================================================================
# PAGE: 2023 vs 2025 Comparison (flagship)
# ===========================================================================

elif page == "2023 vs 2025 Comparison":
    from score_explainer import explain_score_difference

    st.markdown(
        '<span class="system-badge-compare">FLAGSHIP COMPARISON PAGE</span>',
        unsafe_allow_html=True,
    )
    st.markdown("## 2023 vs 2025 Scoring System Comparison")
    st.markdown(
        "Side-by-side analysis of how the methodology change from the 2023 Combined System "
        "to the 2025 Split System (Passive/Active) affected fund scores."
    )

    df_2023 = load_2023_scores()
    df_2025 = get_data()

    if df_2023.empty:
        st.error("scores_2023.csv not found. Cannot render comparison.")
        st.stop()
    if df_2025.empty:
        st.warning("No 2025 data available. Upload a CSV on the **Upload CSV** page.")
        st.stop()

    # Merge datasets
    scored_2025 = df_2025[df_2025[SCORE_COL].notna()].copy()
    merged = df_2023[["Symbol", "Name", "Category Name", "Score_2023"]].merge(
        scored_2025[[SYM_COL, SCORE_COL, TYPE_COL]].rename(columns={SYM_COL: "Symbol"}),
        on="Symbol",
        how="inner"
    )
    merged["Change"] = merged[SCORE_COL] - merged["Score_2023"]
    merged["Score_2025"] = merged[SCORE_COL]

    st.markdown(f"**{len(merged):,}** funds found in both datasets.")

    # ---------------------------------------------------------------------------
    # 1. Scatter Plot: 2023 vs 2025
    # ---------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### 1. Score Migration Scatter Plot")
    st.markdown(
        "X-axis = 2023 score, Y-axis = 2025 score. Points **above** the diagonal improved; "
        "points **below** declined."
    )

    fig_scatter = px.scatter(
        merged,
        x="Score_2023",
        y="Score_2025",
        color=TYPE_COL,
        hover_data={"Symbol": True, "Name": True, "Score_2023": ":.1f", "Score_2025": ":.1f", "Change": ":.1f"},
        color_discrete_map={"Passive": "#4F98A3", "Active": "#8B6FC5"},
        labels={"Score_2023": "Score (2023 Combined System)", "Score_2025": "Score (2025 System)"},
        opacity=0.7,
    )
    # Diagonal "no change" line
    max_val = max(merged["Score_2023"].max(), merged["Score_2025"].max())
    min_val = min(merged["Score_2023"].min(), merged["Score_2025"].min())
    fig_scatter.add_trace(
        go.Scatter(
            x=[min_val, max_val],
            y=[min_val, max_val],
            mode="lines",
            line=dict(color="#4a4845", dash="dash", width=1),
            name="No Change",
            showlegend=True,
        )
    )
    fig_scatter.add_hline(y=80, line_dash="dot", line_color="#4ade80", opacity=0.4)
    fig_scatter.add_hline(y=60, line_dash="dot", line_color="#f87171", opacity=0.4)
    fig_scatter.add_vline(x=80, line_dash="dot", line_color="#4ade80", opacity=0.4)
    fig_scatter.add_vline(x=60, line_dash="dot", line_color="#f87171", opacity=0.4)
    apply_theme(fig_scatter)
    fig_scatter.update_layout(height=580)
    st.plotly_chart(fig_scatter, use_container_width=True)

    # ---------------------------------------------------------------------------
    # 2. Biggest Movers Table
    # ---------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### 2. Biggest Movers")

    col_imp, col_dec = st.columns(2)

    with col_imp:
        st.markdown("#### Top 20 Improvers")
        improvers = merged.nlargest(20, "Change")[
            ["Symbol", "Name", "Category Name", "Score_2023", "Score_2025", "Change", TYPE_COL]
        ].copy()
        improvers["Score_2023"] = improvers["Score_2023"].round(1)
        improvers["Score_2025"] = improvers["Score_2025"].round(1)
        improvers["Change"] = improvers["Change"].round(1)
        st.dataframe(
            improvers.style.map(style_change_col, subset=["Change"])
                           .map(style_score_col, subset=["Score_2025"]),
            use_container_width=True,
            hide_index=True,
            height=560,
        )

    with col_dec:
        st.markdown("#### Top 20 Decliners")
        decliners = merged.nsmallest(20, "Change")[
            ["Symbol", "Name", "Category Name", "Score_2023", "Score_2025", "Change", TYPE_COL]
        ].copy()
        decliners["Score_2023"] = decliners["Score_2023"].round(1)
        decliners["Score_2025"] = decliners["Score_2025"].round(1)
        decliners["Change"] = decliners["Change"].round(1)
        st.dataframe(
            decliners.style.map(style_change_col, subset=["Change"])
                           .map(style_score_col, subset=["Score_2025"]),
            use_container_width=True,
            hide_index=True,
            height=560,
        )

    # ---------------------------------------------------------------------------
    # 3. System Methodology Comparison Table
    # ---------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### 3. System Methodology Comparison")

    methodology_table = pd.DataFrame([
        {
            "Factor": "Expense Ratio Weight",
            "2023 System": "5% (Annual Report ER)",
            "2025 Active": "25% (Net ER)",
            "2025 Passive": "40% (Net ER)",
            "Impact": "Heavily penalizes high-cost active funds; critical for passive",
        },
        {
            "Factor": "Alpha (5Y + 10Y)",
            "2023 System": "22% combined",
            "2025 Active": "Not used",
            "2025 Passive": "Not used",
            "Impact": "Removed — 2025 uses Information Ratio instead",
        },
        {
            "Factor": "Information Ratio (3Y+5Y+10Y)",
            "2023 System": "Not used",
            "2025 Active": "20% combined",
            "2025 Passive": "Not used",
            "Impact": "New — measures consistency of active excess returns",
        },
        {
            "Factor": "Sortino Ratio (3Y+5Y+10Y)",
            "2023 System": "Not used",
            "2025 Active": "20% combined",
            "2025 Passive": "Not used",
            "Impact": "New — risk-adjusted downside measure",
        },
        {
            "Factor": "Manager Tenure",
            "2023 System": "6% combined (median + avg)",
            "2025 Active": "Not used",
            "2025 Passive": "Not used",
            "Impact": "Removed — tenure does not reliably predict returns",
        },
        {
            "Factor": "Total AUM",
            "2023 System": "1.5%",
            "2025 Active": "Not used",
            "2025 Passive": "Not used",
            "Impact": "Removed — share class AUM retained",
        },
        {
            "Factor": "Share Class AUM",
            "2023 System": "2.5%",
            "2025 Active": "6% (higher weight)",
            "2025 Passive": "6%",
            "Impact": "Increased weight for liquidity signal",
        },
        {
            "Factor": "Upside Capture (5Y+10Y)",
            "2023 System": "11% combined",
            "2025 Active": "11% combined",
            "2025 Passive": "Not used",
            "Impact": "Stable weight for active; excluded from passive system",
        },
        {
            "Factor": "Downside Capture (5Y+10Y)",
            "2023 System": "14% combined",
            "2025 Active": "10% combined",
            "2025 Passive": "5% combined",
            "Impact": "Reduced slightly; still important for both systems",
        },
        {
            "Factor": "Max Drawdown (5Y+10Y)",
            "2023 System": "20% combined",
            "2025 Active": "10% combined",
            "2025 Passive": "4% combined",
            "Impact": "Reduced weight; partially replaced by Sortino",
        },
        {
            "Factor": "Returns (5Y+10Y)",
            "2023 System": "18% combined (annualized monthly)",
            "2025 Active": "4% combined (total daily)",
            "2025 Passive": "Not used",
            "Impact": "Much lower weight — superseded by IR and Sortino",
        },
        {
            "Factor": "Tracking Error (3Y+5Y+10Y)",
            "2023 System": "Not used",
            "2025 Active": "Not used",
            "2025 Passive": "30% combined",
            "Impact": "New for passive — measures index-tracking precision",
        },
        {
            "Factor": "R-Squared (5Y)",
            "2023 System": "Not used",
            "2025 Active": "Not used",
            "2025 Passive": "5%",
            "Impact": "New for passive — confirms index-like behavior",
        },
        {
            "Factor": "Fund Type Split",
            "2023 System": "All funds scored together",
            "2025 Active": "Active funds only",
            "2025 Passive": "Passive funds only",
            "Impact": "Separate scoring prevents passive/active distortion",
        },
    ])

    st.dataframe(methodology_table, use_container_width=True, hide_index=True, height=500)

    # ---------------------------------------------------------------------------
    # 4. Fund Comparison Tool
    # ---------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### 4. Fund Comparison Tool")
    st.markdown("Enter a ticker to see a full side-by-side score breakdown and narrative.")

    comp_ticker = st.text_input("Ticker symbol", placeholder="e.g. PRILX", max_chars=10, key="comp_page_ticker")

    if comp_ticker:
        comp_sym = comp_ticker.strip().upper()
        r23 = df_2023[df_2023["Symbol"] == comp_sym]
        r25 = df_2025[df_2025[SYM_COL] == comp_sym]

        if r23.empty and r25.empty:
            st.error(f"No fund found for ticker **{comp_sym}** in either dataset.")
        else:
            with st.spinner(f"Analyzing {comp_sym}…"):
                diff = explain_score_difference(df_2023, df_2025, comp_sym)

            if "error" in diff:
                st.error(diff["error"])
            else:
                s2023 = diff.get("score_2023")
                s2025 = diff.get("score_2025")
                delta = diff.get("delta")
                fund_type = diff.get("fund_type_2025", "Unknown")
                name = diff.get("name", comp_sym)

                # Score display
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown(
                        f'<div class="compare-card-2023">'
                        f'<div style="font-size:0.7rem; color:#f59e0b; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:8px;">2023 Combined System</div>'
                        f'<div style="font-size:3rem; font-weight:800; color:#f59e0b;">{f"{s2023:.1f}" if s2023 else "N/A"}</div>'
                        f'<div style="font-size:0.8rem; color:#7a7875; margin-top:6px;">15 metrics · All funds together</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with c2:
                    score_color = score_color_hex(s2025)
                    band_2025 = get_score_band(s2025)
                    st.markdown(
                        f'<div class="compare-card-2025">'
                        f'<div style="font-size:0.7rem; color:#4F98A3; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:8px;">2025 {fund_type} System</div>'
                        f'<div style="font-size:3rem; font-weight:800; color:{score_color};">{f"{s2025:.1f}" if s2025 else "N/A"}</div>'
                        f'<div style="font-size:0.8rem; color:#7a7875; margin-top:6px;">{len(ACTIVE_METRICS) if fund_type == "Active" else len(PASSIVE_METRICS)} metrics · {fund_type} funds only</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with c3:
                    if delta is not None:
                        d_color = "#4ade80" if delta >= 0 else "#f87171"
                        d_sign = "+" if delta >= 0 else ""
                        direction = "Improved" if delta >= 0 else "Declined"
                        st.markdown(
                            f'<div class="kpi-card">'
                            f'<div style="font-size:0.7rem; color:#7a7875; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:8px;">Score Change</div>'
                            f'<div style="font-size:3rem; font-weight:800; color:{d_color};">{d_sign}{delta:.1f}</div>'
                            f'<div style="font-size:0.8rem; color:{d_color}; margin-top:6px;">{direction} from 2023 to 2025</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                # Fund name
                st.markdown(
                    f'<div style="font-size:1.1rem; font-weight:600; color:#CDCCCA; margin:12px 0;">'
                    f'{name} &nbsp;·&nbsp; <span style="color:#7a7875;">{comp_sym}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # Methodology note
                st.markdown("**Methodology Difference**")
                st.markdown(
                    f'<div style="background:#12161f; border-left:3px solid #4F98A3; '
                    f'padding:12px 18px; font-size:0.88rem; color:#9a9895; margin-bottom:12px;">'
                    f'{diff["methodology_note"]}</div>',
                    unsafe_allow_html=True,
                )

                # 2023-only metrics
                if diff.get("metrics_2023_only"):
                    st.markdown("**Metrics Removed in 2025:**")
                    for m in diff["metrics_2023_only"]:
                        st.markdown(
                            f'<div class="weakness-card">'
                            f'<div class="metric-name" style="color:#f59e0b;">{m["metric"]}</div>'
                            f'<div class="metric-sentence">{m["note"]}</div>'
                            f'<div class="metric-stats">Weight in 2023: {m["weight_2023"]}% → Not used in 2025. '
                            f'2023 contribution: ~{m.get("contribution_2023", 0):.1f} pts</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                # 2025-only metrics
                if diff.get("metrics_2025_only"):
                    st.markdown("**Metrics Added in 2025:**")
                    for m in diff["metrics_2025_only"]:
                        st.markdown(
                            f'<div class="strength-card">'
                            f'<div class="metric-name" style="color:#4F98A3;">{m["metric"]}</div>'
                            f'<div class="metric-sentence">{m["note"]}</div>'
                            f'<div class="metric-stats">Not in 2023 → Weight in 2025: {m["weight_2025"]}%. '
                            f'2025 contribution: ~{m.get("contribution_2025", 0):.1f} pts</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                # Net narrative
                if diff.get("net_narrative"):
                    st.markdown("**Net Analysis**")
                    st.markdown(
                        f'<div style="background:#1C1B19; border:1px solid #2a2927; border-radius:8px; '
                        f'padding:16px 20px; font-size:0.9rem; color:#CDCCCA; line-height:1.8; '
                        f'white-space:pre-line;">'
                        f'{diff["net_narrative"]}</div>',
                        unsafe_allow_html=True,
                    )

                # Shared metrics table
                if diff.get("shared_metrics"):
                    st.markdown("**Shared Metrics — Percentile Comparison:**")
                    sm_df = pd.DataFrame(diff["shared_metrics"])
                    sm_df.columns = ["Metric", "Value (2023)", "Value (2025)", "Percentile (2023)", "Percentile (2025)"]
                    st.dataframe(sm_df, use_container_width=True, hide_index=True)
    else:
        st.info("Try: **PRILX** (decliner), **SCHD** (improver), or **OMCIX**")


# ===========================================================================
# PAGE: PDF Reports
# ===========================================================================

elif page == "PDF Reports":
    from pdf_report import generate_report, generate_single_fund_report

    st.markdown("## PDF Reports")
    st.markdown("Generate professional IC committee-style reports.")

    df = get_data()
    if df.empty:
        st.warning("No data available. Upload a CSV on the **Upload CSV** page.")
        st.stop()

    report_type = st.radio(
        "Report type",
        ["Full Report (all categories)", "Category Report", "Single Fund"],
        horizontal=True,
    )

    if report_type == "Full Report (all categories)":
        report_title = st.text_input("Report title", value="Fund Scoring Report")
        n_cats = st.slider("Number of categories to include", 1, 30, 10)
        top_cats = df[CAT_COL].value_counts().head(n_cats).index.tolist()
        st.caption(f"Will include: {', '.join(top_cats[:5])}{'…' if len(top_cats) > 5 else ''}")

        if st.button("Generate Full Report", type="primary"):
            with st.spinner("Generating PDF…"):
                pdf_bytes = generate_report(df, categories=top_cats, title=report_title)
            st.success(f"Report generated ({len(pdf_bytes):,} bytes)")
            st.download_button(
                "⬇ Download Full Report",
                data=pdf_bytes,
                file_name="fund_scoring_full_report.pdf",
                mime="application/pdf",
            )

    elif report_type == "Category Report":
        all_cats = sorted(df[CAT_COL].dropna().unique())
        selected_cats = st.multiselect(
            "Select categories",
            all_cats,
            default=all_cats[:3] if len(all_cats) >= 3 else all_cats,
        )
        report_title = st.text_input("Report title", value="Category Fund Report")

        if st.button("Generate Category Report", type="primary"):
            if not selected_cats:
                st.warning("Please select at least one category.")
            else:
                with st.spinner("Generating PDF…"):
                    pdf_bytes = generate_report(df, categories=selected_cats, title=report_title)
                st.success(f"Report generated ({len(pdf_bytes):,} bytes)")
                st.download_button(
                    "⬇ Download Category Report",
                    data=pdf_bytes,
                    file_name="fund_scoring_category_report.pdf",
                    mime="application/pdf",
                )

    else:  # Single Fund
        fund_input = st.text_input("Enter ticker symbol", placeholder="e.g. SCHD", max_chars=10)

        if fund_input:
            symbol = fund_input.strip().upper()
            match = df[df[SYM_COL] == symbol]
            if match.empty:
                st.error(f"No fund found for ticker **{symbol}**.")
            else:
                row = match.iloc[0]
                st.markdown(
                    f"**{row.get(NAME_COL, symbol)}** · "
                    f"{row.get(TYPE_COL, '—')} · "
                    f"{row.get(CAT_COL, '—')} · "
                    f"Score: **{fmt_score(row.get(SCORE_COL))}**"
                )
                if st.button(f"Generate Report for {symbol}", type="primary"):
                    with st.spinner(f"Generating PDF for {symbol}…"):
                        pdf_bytes = generate_single_fund_report(df, symbol)
                    st.success(f"Report generated ({len(pdf_bytes):,} bytes)")
                    st.download_button(
                        f"⬇ Download {symbol} Report",
                        data=pdf_bytes,
                        file_name=f"fund_report_{symbol.lower()}.pdf",
                        mime="application/pdf",
                    )
        else:
            st.info("Enter a ticker symbol above to generate a single-fund report.")


# ===========================================================================
# PAGE: History
# ===========================================================================

elif page == "History":
    from history_tracker import (
        compare_snapshots,
        get_fund_history,
        list_snapshots,
        save_snapshot,
    )

    st.markdown("## Historical Tracking")
    st.markdown("Save score snapshots over time and track fund performance trends.")

    df = get_data()
    if df.empty:
        st.warning("No data available. Upload a CSV on the **Upload CSV** page.")
        st.stop()

    # Save snapshot section
    with st.expander("Save Current Snapshot", expanded=True):
        label_input = st.text_input("Snapshot label", placeholder="e.g. March 2026")
        if st.button("Save Snapshot", type="primary"):
            with st.spinner("Saving snapshot…"):
                date_id = save_snapshot(df, label=label_input if label_input else None)
            st.success(f"Snapshot saved with ID: {date_id}")

    st.markdown("---")

    # List all snapshots
    snapshots = list_snapshots()

    if not snapshots:
        st.info("No snapshots saved yet. Use the section above to save your first snapshot.")
        st.stop()

    st.markdown("### Saved Snapshots")
    snap_df = pd.DataFrame(snapshots)
    snap_df["avg_score"] = snap_df["avg_score"].apply(lambda x: f"{x:.1f}" if x is not None else "—")
    st.dataframe(snap_df.rename(columns={
        "date": "Date", "label": "Label",
        "fund_count": "Funds", "avg_score": "Avg Score"
    }), use_container_width=True, hide_index=True)

    if len(snapshots) >= 2:
        st.markdown("---")
        st.markdown("### Compare Two Snapshots")
        snap_dates = [s["date"] for s in snapshots]
        snap_labels = [f"{s['date']} — {s['label']}" for s in snapshots]

        c1, c2 = st.columns(2)
        with c1:
            idx1 = st.selectbox("Earlier snapshot", range(len(snap_labels)), format_func=lambda i: snap_labels[i], index=min(1, len(snap_labels) - 1))
        with c2:
            idx2 = st.selectbox("Later snapshot", range(len(snap_labels)), format_func=lambda i: snap_labels[i], index=0)

        if st.button("Compare Snapshots"):
            date1 = snap_dates[idx1]
            date2 = snap_dates[idx2]
            if date1 == date2:
                st.warning("Please select two different snapshots.")
            else:
                with st.spinner("Comparing snapshots…"):
                    try:
                        changes_df = compare_snapshots(date1, date2)
                    except Exception as e:
                        st.error(f"Error comparing snapshots: {e}")
                        changes_df = pd.DataFrame()

                if not changes_df.empty:
                    st.markdown(f"**{len(changes_df):,} funds compared** — sorted by largest score change")

                    top_movers = changes_df.dropna(subset=["Change"]).head(30)
                    st.dataframe(
                        top_movers.style.map(style_change_col, subset=["Change"]),
                        use_container_width=True,
                        height=460,
                        hide_index=True,
                    )

                    csv_out = changes_df.to_csv(index=False).encode()
                    st.download_button(
                        "⬇ Download Full Comparison CSV",
                        data=csv_out,
                        file_name=f"score_comparison_{date1}_vs_{date2}.csv",
                        mime="text/csv",
                    )
                else:
                    st.info("No overlapping funds found between the two snapshots.")

    # Fund history chart
    st.markdown("---")
    st.markdown("### Fund Score History")
    hist_input = st.text_input("Enter ticker symbol to view history", placeholder="e.g. SCHD", max_chars=10)

    if hist_input:
        hist_symbol = hist_input.strip().upper()
        with st.spinner(f"Loading history for {hist_symbol}…"):
            history = get_fund_history(df, hist_symbol)

        if not history:
            st.info(f"No snapshot history found for **{hist_symbol}**. Save more snapshots over time to track trends.")
        else:
            hist_df = pd.DataFrame(history)
            hist_df["date"] = pd.to_datetime(hist_df["date"])
            hist_df = hist_df.sort_values("date")

            st.markdown(f"**{hist_symbol}** — {len(hist_df)} snapshot(s) found")

            if len(hist_df) == 1:
                st.metric("Score", f"{hist_df.iloc[0]['score']:.1f}" if hist_df.iloc[0]['score'] else "—")
            else:
                fig_line = px.line(
                    hist_df,
                    x="date",
                    y="score",
                    markers=True,
                    labels={"date": "Date", "score": "Score"},
                    title=f"{hist_symbol} — Score Over Time",
                )
                fig_line.add_hline(y=80, line_dash="dash", line_color="#4ade80", annotation_text="STRONG threshold")
                fig_line.add_hline(y=60, line_dash="dash", line_color="#f87171", annotation_text="WEAK threshold")
                apply_theme(fig_line)
                st.plotly_chart(fig_line, use_container_width=True)

            st.dataframe(
                hist_df[["date", "label", "score", "band"]].rename(
                    columns={"date": "Date", "label": "Label", "score": "Score", "band": "Band"}
                ),
                use_container_width=True,
                hide_index=True,
            )


# ===========================================================================
# PAGE: Monthly Workflow
# ===========================================================================

elif page == "Monthly Workflow":
    import datetime as _dt

    import workflow_ui

    st.markdown("## Monthly Workflow")
    st.caption(
        "Upload paired YCharts exports, validate, archive a dated run, preview the "
        "dual-score table, optionally compare against the prior run, and export "
        "the Excel audit workbook."
    )
    st.info(
        "**Note:** Run archives are written to the local filesystem "
        "(`streamlit/runs/YYYY-MM-DD/`). On Streamlit Cloud the filesystem is "
        "ephemeral — archives do not persist across container restarts unless "
        "the app is configured with a persistent/shared directory.",
        icon="ℹ️",
    )

    # ---- Session state ----
    _ss = st.session_state
    _ss.setdefault("mw_last_run_date", None)
    _ss.setdefault("mw_intake_report", None)
    _ss.setdefault("mw_upload_tmpdir", None)

    # ---- Step 1: Upload + run date ----
    st.markdown("### 1 · Upload & Run Date")
    c1, c2 = st.columns(2)
    with c1:
        file_2025 = st.file_uploader(
            "YCharts 2025 export (CSV)",
            type=["csv"], key="mw_file_2025",
        )
    with c2:
        file_2023 = st.file_uploader(
            "YCharts 2023 export (CSV)",
            type=["csv"], key="mw_file_2023",
        )
    c3, c4 = st.columns([1, 1])
    with c3:
        run_date = st.date_input(
            "Run date",
            value=_dt.date.today(),
            key="mw_run_date",
        ).isoformat()
    with c4:
        overwrite = st.checkbox(
            "Overwrite if run exists", value=False, key="mw_overwrite",
        )
    notes = st.text_input(
        "Notes (optional, stored in run metadata)", value="", key="mw_notes",
    )

    # ---- Step 2: Validate ----
    st.markdown("### 2 · Intake Validation")
    validate_btn = st.button(
        "Run Validation (Preflight)",
        disabled=(file_2025 is None or file_2023 is None),
        key="mw_btn_validate",
    )
    if validate_btn:
        workflow_ui.cleanup_tmp(_ss.get("mw_upload_tmpdir"))
        p25, p23, tmp = workflow_ui.persist_uploads(
            file_2025.getvalue(), file_2023.getvalue(),
        )
        _ss["mw_upload_tmpdir"] = tmp
        _ss["mw_upload_paths"] = (p25, p23)
        with st.spinner("Validating uploaded files…"):
            _ss["mw_intake_report"] = workflow_ui.run_intake(p25, p23)

    intake = _ss.get("mw_intake_report")
    if intake:
        counts = intake.get("finding_counts", {})
        status = "FAIL" if intake.get("failed") else "PASS"
        st.markdown(
            f"**Status:** `{status}` · errors {counts.get('error', 0)} · "
            f"warnings {counts.get('warning', 0)} · info {counts.get('info', 0)}"
        )
        join = intake.get("join") or {}
        if join.get("available"):
            st.caption(
                f"Symbol overlap: {join['symbols_common']:,} common · "
                f"{join['symbols_only_2025']:,} 2025-only · "
                f"{join['symbols_only_2023']:,} 2023-only "
                f"({join['overlap_rate_vs_smaller'] * 100:.1f}%)"
            )
        with st.expander("Validation details"):
            st.code(intake.get("summary_text", ""), language="text")

    # ---- Step 3: Archive ----
    st.markdown("### 3 · Build Table & Create Run Archive")
    archive_btn = st.button(
        "Create Run Archive",
        disabled=(_ss.get("mw_upload_paths") is None),
        key="mw_btn_archive",
        type="primary",
    )
    if archive_btn:
        p25, p23 = _ss["mw_upload_paths"]
        try:
            with st.spinner("Building dual-score table and writing archive…"):
                run = workflow_ui.create_archive_from_uploads(
                    path_2025=p25,
                    path_2023=p23,
                    run_date=run_date,
                    overwrite=overwrite,
                    preflight="warn",
                    notes=notes or None,
                )
            _ss["mw_last_run_date"] = run_date
            st.success(
                f"Archive created for {run_date} · "
                f"{run['validation'].get('row_count', 0):,} rows · "
                f"path `{run['path']}`"
            )
        except FileExistsError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Archive creation failed: {exc}")

    # ---- Step 4: Previews from latest (or last-created) run ----
    st.markdown("### 4 · Dual-Score Table Previews")
    from run_archive import load_run as _load_run  # local import, avoids top-of-file churn

    active_date = _ss.get("mw_last_run_date")
    run = None
    if active_date:
        try:
            run = _load_run(active_date)
        except Exception:
            run = None
    if run is None:
        run = workflow_ui.load_latest()

    if run is None:
        st.caption("No archived runs found yet — create one above.")
    else:
        val = run.get("validation") or {}
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.metric("Run Date", run.get("run_date", "—"))
        with k2:
            st.metric("Rows", f"{val.get('row_count', 0):,}")
        with k3:
            s25 = val.get("score_2025", {}) or {}
            st.metric(
                "Avg Score 2025",
                f"{s25.get('mean'):.1f}" if s25.get("mean") is not None else "—",
            )
        with k4:
            s23 = val.get("score_2023", {}) or {}
            st.metric(
                "Avg Score 2023",
                f"{s23.get('mean'):.1f}" if s23.get("mean") is not None else "—",
            )

        previews = workflow_ui.top_previews(run["table"])
        tab1, tab2, tab3, tab4 = st.tabs(
            ["Top 50 · 2023", "Top 50 · 2025", "Top 50 · Consensus", "Top 50 · Disagreement"]
        )
        with tab1:
            st.dataframe(previews["top_2023"], use_container_width=True, hide_index=True)
        with tab2:
            st.dataframe(previews["top_2025"], use_container_width=True, hide_index=True)
        with tab3:
            st.dataframe(previews["top_consensus"], use_container_width=True, hide_index=True)
        with tab4:
            st.dataframe(previews["disagreement"], use_container_width=True, hide_index=True)

    # ---- Step 4b: Model Holdings Overlay (optional) ----
    st.markdown("### 4b · Model Holdings Overlay (optional)")
    st.caption(
        "Upload current model portfolio holdings to see how they stack up "
        "against the scored fund universe. The overlay is a lens on top of "
        "the dual-score table — not part of the scoring methodology. "
        "Expected columns: **Model_Name**, **Symbol**, **Target_Weight** "
        "(percent or fraction). Optional: Fund_Name, Sleeve, Status, "
        "Internal_Category, Notes."
    )
    _ss.setdefault("mw_models_report", None)
    _ss.setdefault("mw_models_tmpdir", None)
    _ss.setdefault("mw_models_path", None)
    _ss.setdefault("mw_overlay_date", None)

    mh_file = st.file_uploader(
        "Current model holdings (CSV)",
        type=["csv"], key="mw_file_models",
    )

    active_mh_date = _ss.get("mw_last_run_date")
    if active_mh_date is None:
        _mh_runs = workflow_ui.available_runs()
        if _mh_runs:
            active_mh_date = _mh_runs[-1]

    mh_cols = st.columns([1, 1])
    with mh_cols[0]:
        validate_mh_btn = st.button(
            "Validate Holdings",
            disabled=(mh_file is None or active_mh_date is None),
            key="mw_btn_validate_models",
        )
    with mh_cols[1]:
        build_overlay_btn = st.button(
            "Build Overlay Artifacts",
            disabled=(
                mh_file is None or active_mh_date is None
                or _ss.get("mw_models_report") is None
                or _ss.get("mw_models_report", {}).get("failed", True)
            ),
            key="mw_btn_build_overlay",
            type="primary",
        )

    if validate_mh_btn and mh_file is not None and active_mh_date:
        workflow_ui.cleanup_tmp(_ss.get("mw_models_tmpdir"))
        path, tmp = workflow_ui.persist_model_holdings_upload(mh_file.getvalue())
        _ss["mw_models_tmpdir"] = tmp
        _ss["mw_models_path"] = path
        try:
            run_for_intake = _load_run(active_mh_date)
            _ss["mw_models_report"] = workflow_ui.run_model_holdings_intake(
                path, dual_table=run_for_intake["table"],
            )
        except Exception as exc:
            st.error(f"Model holdings validation failed: {exc}")

    mh_report = _ss.get("mw_models_report")
    if mh_report:
        counts = mh_report.get("finding_counts", {})
        status = "FAIL" if mh_report.get("failed") else "PASS"
        st.markdown(
            f"**Holdings status:** `{status}` · errors {counts.get('error', 0)} · "
            f"warnings {counts.get('warning', 0)} · info {counts.get('info', 0)}"
        )
        coverage = mh_report.get("coverage") or {}
        if coverage.get("available"):
            st.caption(
                f"Universe coverage: {coverage['covered_rows']:,}/"
                f"{coverage['total_rows']:,} rows "
                f"({coverage['coverage_rate'] * 100:.1f}%)  ·  "
                f"models: {len(mh_report.get('model_names') or [])}"
            )
        with st.expander("Holdings validation details"):
            st.code(mh_report.get("summary_text", ""), language="text")

    if build_overlay_btn and _ss.get("mw_models_path") and active_mh_date:
        try:
            with st.spinner("Building model holdings overlay…"):
                overlay = workflow_ui.generate_model_overlay_for_run(
                    holdings_path=_ss["mw_models_path"],
                    run_date=active_mh_date,
                )
            _ss["mw_overlay_date"] = active_mh_date
            st.success(
                f"Overlay generated for {active_mh_date} · "
                f"{overlay['metadata'].get('model_count', 0)} model(s) · "
                f"{overlay['metadata'].get('holding_row_count', 0)} holdings · "
                f"path `{overlay['path']}`"
            )
        except Exception as exc:
            st.error(f"Overlay build failed: {exc}")

    overlay_date = _ss.get("mw_overlay_date") or active_mh_date
    if overlay_date:
        loaded = workflow_ui.load_model_overlay_for_run(overlay_date)
        if loaded is not None:
            st.markdown(f"**Overlay artifacts for {overlay_date}:**")
            tab_s, tab_r, tab_w, tab_c = st.tabs([
                "Model Stack-Up", "Current Holdings Review",
                "Weak Links", "Top Candidates Not Used",
            ])
            with tab_s:
                st.dataframe(
                    loaded.get("summary", pd.DataFrame()),
                    use_container_width=True, hide_index=True,
                )
            with tab_r:
                review_df = loaded.get("current_review", pd.DataFrame())
                st.dataframe(review_df, use_container_width=True, hide_index=True)
            with tab_w:
                scorecard_df = loaded.get("scorecard", pd.DataFrame())
                weak = scorecard_df[
                    scorecard_df["Overlay_Action"].isin(
                        ["Replacement_Candidate", "Review_Missing_Score"]
                    )
                ] if not scorecard_df.empty else scorecard_df
                st.dataframe(weak, use_container_width=True, hide_index=True)
            with tab_c:
                st.dataframe(
                    loaded.get("research_candidates", pd.DataFrame()),
                    use_container_width=True, hide_index=True,
                )
                st.caption("Same-category replacement suggestions:")
                st.dataframe(
                    loaded.get("replacement_candidates", pd.DataFrame()),
                    use_container_width=True, hide_index=True,
                )

    # ---- Step 4c: Replacement Workbench (per-ticker research) ----
    st.markdown("### 4c · Replacement Workbench (per-ticker)")
    st.caption(
        "One-off research view for **replacing a single model holding**. "
        "Separate from the monthly committee packet — the overlay above "
        "scans every model; this workbench answers 'if one holding isn't "
        "acceptable, what should replace it?' with a focused same-category "
        "short list. Share-class aliases (e.g. `PRBLX` → `PRILX`) are "
        "applied automatically."
    )

    _ss.setdefault("mw_rw_last_ticker", None)
    _ss.setdefault("mw_rw_last_run_date", None)

    rw_run_date = _ss.get("mw_overlay_date") or _ss.get("mw_last_run_date")
    if rw_run_date is None:
        _rw_runs = workflow_ui.available_runs()
        if _rw_runs:
            rw_run_date = _rw_runs[-1]

    if rw_run_date is None:
        st.caption("Create a run archive above to enable the workbench.")
    else:
        try:
            rw_run = _load_run(rw_run_date)
            rw_universe = rw_run["table"]
        except Exception:
            rw_run = None
            rw_universe = pd.DataFrame()

        rw_holdings = workflow_ui.model_holding_symbols_for_run(rw_run_date)

        rw_cols = st.columns([1.3, 1, 1, 1])
        with rw_cols[0]:
            if not rw_holdings.empty and "Symbol" in rw_holdings.columns:
                holding_choices = sorted(
                    rw_holdings["Symbol"].dropna().astype(str).unique()
                )
                preselect = 0
                if "PRBLX" in holding_choices:
                    preselect = holding_choices.index("PRBLX")
                picked = st.selectbox(
                    "Select current holding",
                    options=holding_choices,
                    index=preselect,
                    key="mw_rw_picked",
                )
                manual = st.text_input(
                    "…or type a ticker (overrides selection)",
                    value="",
                    key="mw_rw_manual",
                )
                rw_ticker = (manual or picked or "").strip().upper()
            else:
                st.caption(
                    "No overlay scorecard found for this run — type a ticker "
                    "directly to research."
                )
                manual = st.text_input(
                    "Ticker to replace",
                    value="PRBLX",
                    key="mw_rw_manual_no_overlay",
                )
                rw_ticker = (manual or "").strip().upper()
        with rw_cols[1]:
            rw_top_n = st.number_input(
                "Top-N candidates",
                min_value=3, max_value=50, value=10, step=1,
                key="mw_rw_top_n",
            )
        with rw_cols[2]:
            pass  # Category override moved to discovery-filters block below.
        with rw_cols[3]:
            rw_exclude_held = st.checkbox(
                "Exclude already-held", value=False, key="mw_rw_exclude",
            )

        # ---- Inferred category / fund-type discovery filters ----------------
        # Resolve aliases (e.g. PRBLX -> PRILX) and pull the holding's
        # category + fund_type so the user can see what discovery would
        # default to before they kick off the build.
        rw_inferred_category: Optional[str] = None
        rw_inferred_fund_type: Optional[str] = None
        if rw_ticker:
            try:
                from symbol_aliases import (
                    load_default_aliases as _load_aliases_for_infer,
                    resolve_symbol as _resolve_for_infer,
                )

                _alias_map = _load_aliases_for_infer()
                _universe_set: set = set()
                if (
                    rw_universe is not None
                    and not rw_universe.empty
                    and "Symbol" in rw_universe.columns
                ):
                    _universe_set = {
                        str(s).strip().upper()
                        for s in rw_universe["Symbol"].dropna().astype(str).tolist()
                    }
                _resolved_for_infer = _resolve_for_infer(
                    rw_ticker, _alias_map, _universe_set,
                )
                if (
                    _resolved_for_infer
                    and rw_universe is not None
                    and not rw_universe.empty
                    and "Symbol" in rw_universe.columns
                ):
                    _sym_u = (
                        rw_universe["Symbol"].astype(str).str.strip().str.upper()
                    )
                    _hit = rw_universe.loc[_sym_u == _resolved_for_infer]
                    if not _hit.empty:
                        _row0 = _hit.iloc[0]
                        if "Category" in rw_universe.columns:
                            _cat = _row0.get("Category")
                            if pd.notna(_cat) and str(_cat).strip():
                                rw_inferred_category = str(_cat).strip()
                        if "Fund_Type" in rw_universe.columns:
                            _ft = _row0.get("Fund_Type")
                            if pd.notna(_ft) and str(_ft).strip():
                                rw_inferred_fund_type = str(_ft).strip()
            except Exception:
                rw_inferred_category = None
                rw_inferred_fund_type = None

        st.markdown("**Discovery filters**")
        st.caption(
            "When you research a replacement, the workbench infers the "
            "current holding's Morningstar **category** and **fund type** "
            "(active / passive) from the scored universe and applies them "
            "as filters by default. For PRBLX → PRILX, that defaults to "
            "**Active + Large Blend**, so passive Large Blend names won't "
            "surface unless you override below. *Committee candidate lists, "
            "if uploaded, remain authoritative — these filters do not drop "
            "user-supplied committee candidates.*"
        )
        if rw_ticker:
            _inf_msg_bits = []
            _inf_msg_bits.append(
                f"category `{rw_inferred_category or 'unknown'}`"
            )
            _inf_msg_bits.append(
                f"fund type `{rw_inferred_fund_type or 'unknown'}`"
            )
            st.caption(
                f"Inferred for **{rw_ticker}**: " + ", ".join(_inf_msg_bits)
                + (
                    " — discovery will default to these unless overridden."
                    if (rw_inferred_category or rw_inferred_fund_type)
                    else " — no scored-universe metadata; filters will be "
                    "skipped (graceful degrade)."
                )
            )

        df_cols = st.columns([1.4, 1.2, 1])
        with df_cols[0]:
            _cat_default = rw_inferred_category or ""
            rw_category = st.text_input(
                "Category filter (defaults to inferred)",
                value=_cat_default,
                key="mw_rw_category",
                help=(
                    "Leave blank or type 'All' to disable category "
                    "filtering. Defaults to the inferred Morningstar "
                    "category for the current holding."
                ),
            )
        with df_cols[1]:
            ft_options = ["Inferred", "Active", "Passive", "All"]
            rw_ft_choice = st.selectbox(
                "Fund type filter",
                options=ft_options,
                index=0,
                key="mw_rw_ft_choice",
                help=(
                    "Inferred uses the current holding's fund type "
                    "(e.g. PRBLX → Active). Choose Active/Passive to force "
                    "a specific type. All disables the fund-type filter."
                ),
            )
        with df_cols[2]:
            rw_apply_filters_in_committee = st.checkbox(
                "Apply filters even with committee list",
                value=False,
                key="mw_rw_apply_filters_committee",
                help=(
                    "Off (default): an uploaded committee candidate list "
                    "is authoritative — category/fund-type filters are NOT "
                    "forced and committee-supplied symbols won't be dropped. "
                    "On: filters apply on top of the committee list "
                    "(useful for diagnostic review)."
                ),
            )

        # Translate the radio into the workbench API.
        if rw_ft_choice == "All":
            rw_fund_type_override = "All"
            rw_apply_fund_type_filter = False
        elif rw_ft_choice == "Active":
            rw_fund_type_override = "Active"
            rw_apply_fund_type_filter = True
        elif rw_ft_choice == "Passive":
            rw_fund_type_override = "Passive"
            rw_apply_fund_type_filter = True
        else:  # "Inferred"
            rw_fund_type_override = None
            rw_apply_fund_type_filter = None  # default behavior

        # Category selector: blank or "All" disables the category filter.
        _cat_clean = (rw_category or "").strip()
        if _cat_clean.lower() in {"all", "any", ""}:
            rw_category_override = None
            rw_apply_category_filter = False if _cat_clean else None
        else:
            rw_category_override = _cat_clean
            rw_apply_category_filter = True

        # --- Committee candidate list (authoritative replacement universe) ---
        from candidate_list_intake import (
            candidate_list_template_csv as _cand_list_template,
            parse_candidate_list as _parse_candidate_list,
            summarize_report as _summarize_candidate_list_report,
            validate_candidate_list as _validate_candidate_list,
        )

        st.markdown(
            "**Replacement candidates CSV** *(optional, recommended for "
            "committee briefs)*"
        )
        st.caption(
            "Upload the actual names under consideration for replacing "
            "this holding. **When provided, the brief uses ONLY these "
            "candidates** — the full same-category universe is no longer "
            "used for staff-facing output. This is separate from the "
            "Candidate exposures CSV below, which is for benchmark-fit / "
            "stylebox / sector calculations. "
            "Minimum schema: a symbol column named `Symbol`, `Ticker`, "
            "`Fund Symbol`, or `Candidate Symbol` (case-insensitive). "
            "Optional columns preserved when present: `Name`, `Notes`, "
            "`Rationale`, `Active_Passive`, `Fund_Type`, `Category`."
        )
        cl_cols = st.columns([2, 1])
        with cl_cols[0]:
            cand_list_file = st.file_uploader(
                "Replacement candidates CSV (optional, recommended for committee briefs)",
                type=["csv"],
                key="mw_rw_candidate_list",
            )
        with cl_cols[1]:
            st.download_button(
                "⬇︎ Template CSV",
                data=_cand_list_template().encode("utf-8"),
                file_name="replacement_candidates_template.csv",
                mime="text/csv",
                help=(
                    "Minimum-schema template — Symbol column is required, "
                    "all other columns optional."
                ),
                key="mw_rw_cl_template_dl",
            )

        rw_candidate_list = None
        if cand_list_file is not None:
            try:
                rw_candidate_list = _parse_candidate_list(cand_list_file)
                cl_report = _validate_candidate_list(
                    rw_candidate_list, source_label="candidate_list",
                )
                if cl_report["failed"]:
                    st.error(_summarize_candidate_list_report(cl_report))
                elif cl_report["warnings"]:
                    st.warning(_summarize_candidate_list_report(cl_report))
                else:
                    st.caption(_summarize_candidate_list_report(cl_report))
                if rw_candidate_list is not None and not rw_candidate_list.empty:
                    st.caption(
                        f"**Authoritative candidate set:** "
                        f"{len(rw_candidate_list)} symbol(s) — "
                        + ", ".join(
                            "`" + s + "`"
                            for s in rw_candidate_list["Symbol"]
                            .astype(str).head(15).tolist()
                        )
                        + ("…" if len(rw_candidate_list) > 15 else "")
                    )
            except Exception as exc:
                st.error(f"Failed to parse candidate list: {exc}")
                rw_candidate_list = None

        # --- Optional benchmark-fit / portfolio-alignment uploads ---
        with st.expander(
            "Benchmark-fit (optional) — upload exposures to score "
            "candidates by drift vs the static 100/0 equity benchmark",
            expanded=False,
        ):
            from benchmark_fit import (
                DEFAULT_BENCHMARK_WEIGHTS as _DEFAULT_BENCH_WEIGHTS,
            )
            from exposure_intake import (
                parse_exposures as _parse_exposures,
                summarize_report as _summarize_report,
                validate_exposures as _validate_exposures,
            )

            st.caption(
                "Upload three YCharts wide-format exposure exports "
                "(Symbol, Name, 9 stylebox cols, 11 sector cols). The "
                "benchmark uses the static default weights below — these "
                "represent a globally-diversified 100/0 equity sleeve and "
                "apply to every risk-tier model (lower-risk models are "
                "scaled versions of the same equity sleeve)."
            )
            st.caption(
                "**Candidate ideas exposures** is treated as the **curated "
                "replacement universe**: when supplied, the staff-facing "
                "Top Candidates and Benchmark-Fit ranking are restricted "
                "to those tickers (e.g. only the active mutual funds / "
                "ETFs you screened upstream). **Already-held model "
                "positions are excluded by default** so passive sleeve "
                "names (e.g. SPYM in the 100/0 model) cannot be "
                "recommended as a replacement for an active holding "
                "that sits alongside them. Display names are taken "
                "from the candidate file when present."
            )
            ex_cols = st.columns(3)
            with ex_cols[0]:
                model_exp_file = st.file_uploader(
                    "Model holdings exposures (100/0)",
                    type=["csv"], key="mw_rw_model_exp",
                )
            with ex_cols[1]:
                bench_exp_file = st.file_uploader(
                    "Benchmark constituents exposures",
                    type=["csv"], key="mw_rw_bench_exp",
                )
            with ex_cols[2]:
                cand_exp_file = st.file_uploader(
                    "Candidate ideas exposures",
                    type=["csv"], key="mw_rw_cand_exp",
                )

            holdings_file = st.file_uploader(
                "Model holdings library (CSV with Model_Name, Symbol, "
                "Target_Weight) — defaults to model_holdings_master_library_converted.csv",
                type=["csv"], key="mw_rw_holdings_file",
            )

            st.markdown("**Default benchmark weights**")
            bench_weights_text = st.text_area(
                "One SYMBOL=weight per line (weights as decimals).",
                value="\n".join(
                    f"{k}={v:g}" for k, v in _DEFAULT_BENCH_WEIGHTS.items()
                ),
                key="mw_rw_bench_weights_text",
                height=120,
            )

            def _parse_weight_text(text: str):
                out: Dict[str, float] = {}
                for line in (text or "").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, _, v = line.partition("=")
                    elif "," in line:
                        k, _, v = line.partition(",")
                    else:
                        parts = line.split()
                        if len(parts) != 2:
                            continue
                        k, v = parts
                    try:
                        out[k.strip().upper()] = float(v.strip())
                    except ValueError:
                        continue
                return out

            rw_bench_weights = _parse_weight_text(bench_weights_text) \
                or dict(_DEFAULT_BENCH_WEIGHTS)
            total_w = sum(rw_bench_weights.values())
            if abs(total_w - 1.0) > 0.05:
                st.warning(
                    f"Benchmark weights sum to {total_w:.3f} — expected ~1.00."
                )

            st.markdown("**Curated-universe behavior**")
            uni_mode = st.radio(
                "Candidate universe",
                options=["auto", "uploaded", "scored"],
                index=0,
                horizontal=True,
                key="mw_rw_uni_mode",
                help=(
                    "auto: restrict to the uploaded candidate file when one "
                    "is provided, else fall back to the scored universe. "
                    "uploaded: always restrict to the uploaded candidate "
                    "file (curated active-replacement universe). "
                    "scored: ignore the curated file and rank against the "
                    "full scored universe (legacy behavior)."
                ),
            )
            include_held = st.checkbox(
                "Include already-held names in candidate list",
                value=False,
                key="mw_rw_include_held",
                help=(
                    "By default already-held model positions (e.g. SPYM "
                    "in the 100/0 model) are excluded from staff-facing "
                    "replacement recommendations — only the holding being "
                    "replaced is allowed. Toggle this on for diagnostic "
                    "review or when intentionally double-checking passive "
                    "exposures."
                ),
            )

            # Parse + validate any uploaded exposures.
            rw_model_exp = None
            rw_bench_exp = None
            rw_cand_exp = None
            rw_model_holdings = None

            if model_exp_file is not None:
                try:
                    rw_model_exp = _parse_exposures(model_exp_file)
                    rep = _validate_exposures(
                        rw_model_exp, source_label="model_exposures",
                    )
                    if rep["failed"]:
                        st.error(_summarize_report(rep))
                    elif rep["warnings"]:
                        st.warning(_summarize_report(rep))
                    else:
                        st.caption(_summarize_report(rep))
                except Exception as exc:
                    st.error(f"Failed to parse model exposures: {exc}")
                    rw_model_exp = None
            if bench_exp_file is not None:
                try:
                    rw_bench_exp = _parse_exposures(bench_exp_file)
                    rep = _validate_exposures(
                        rw_bench_exp, source_label="benchmark_exposures",
                    )
                    if rep["failed"]:
                        st.error(_summarize_report(rep))
                    elif rep["warnings"]:
                        st.warning(_summarize_report(rep))
                    else:
                        st.caption(_summarize_report(rep))
                except Exception as exc:
                    st.error(f"Failed to parse benchmark exposures: {exc}")
                    rw_bench_exp = None
            if cand_exp_file is not None:
                try:
                    rw_cand_exp = _parse_exposures(cand_exp_file)
                    rep = _validate_exposures(
                        rw_cand_exp, source_label="candidate_exposures",
                    )
                    if rep["failed"]:
                        st.error(_summarize_report(rep))
                    elif rep["warnings"]:
                        st.warning(_summarize_report(rep))
                    else:
                        st.caption(_summarize_report(rep))
                except Exception as exc:
                    st.error(f"Failed to parse candidate exposures: {exc}")
                    rw_cand_exp = None
            if holdings_file is not None:
                try:
                    rw_model_holdings = pd.read_csv(holdings_file)
                except Exception as exc:
                    st.error(f"Failed to parse holdings library: {exc}")
                    rw_model_holdings = None

            rw_fit_ready = (
                rw_model_exp is not None
                and rw_bench_exp is not None
                and rw_model_holdings is not None
            )
            if rw_fit_ready:
                st.success(
                    "Benchmark-fit inputs ready. Drift columns + the "
                    "exposure artifacts will be generated when you build "
                    "the workbench."
                )
            else:
                st.caption(
                    "Upload model exposures, benchmark exposures, and a "
                    "model holdings library to enable benchmark-fit "
                    "ranking. Without them, the workbench runs as before."
                )

        build_rw = st.button(
            "Build Replacement Short List",
            disabled=(not rw_ticker),
            key="mw_btn_build_rw",
            type="primary",
        )
        if build_rw and rw_ticker:
            # If a holdings library was uploaded but exposures weren't,
            # we still pass holdings=None so the fit layer stays off.
            rw_holdings_filtered = None
            if rw_fit_ready and rw_model_holdings is not None:
                if "Model_Name" in rw_model_holdings.columns:
                    h = rw_model_holdings[
                        rw_model_holdings["Model_Name"].astype(str).str.strip()
                        == "100/0"
                    ].copy()
                    rw_holdings_filtered = h if not h.empty else rw_model_holdings
                else:
                    rw_holdings_filtered = rw_model_holdings

            try:
                with st.spinner(f"Researching replacements for {rw_ticker}…"):
                    # When the user opts in to "Apply filters even with
                    # committee list", force the category + fund-type
                    # filters on top of the committee list. Default
                    # (off) preserves PR #20: committee list authoritative.
                    if rw_candidate_list is not None and not rw_apply_filters_in_committee:
                        _apply_cat = False
                        _apply_ft = False
                    else:
                        _apply_cat = rw_apply_category_filter
                        _apply_ft = rw_apply_fund_type_filter

                    rw_bundle = workflow_ui.generate_replacement_workbench_for_run(
                        run_date=rw_run_date,
                        ticker=rw_ticker,
                        category_override=rw_category_override,
                        top_n=int(rw_top_n),
                        exclude_held=rw_exclude_held,
                        persist=True,
                        model_holdings=rw_holdings_filtered if rw_fit_ready else None,
                        model_exposures=rw_model_exp if rw_fit_ready else None,
                        benchmark_exposures=rw_bench_exp if rw_fit_ready else None,
                        benchmark_weights=rw_bench_weights if rw_fit_ready else None,
                        candidate_exposures=rw_cand_exp,
                        candidate_list=rw_candidate_list,
                        candidate_universe_mode=uni_mode,
                        exclude_already_held=(False if include_held else None),
                        fund_type_override=rw_fund_type_override,
                        apply_fund_type_filter=_apply_ft,
                        apply_category_filter=_apply_cat,
                    )
                _ss["mw_rw_last_ticker"] = rw_ticker
                _ss["mw_rw_last_run_date"] = rw_run_date
                resolved = rw_bundle["summary"]["resolved_ticker"]
                alias_note = ""
                if rw_bundle["summary"].get("alias_applied"):
                    alias_note = f" (resolved to `{resolved}` via alias)"
                st.success(
                    f"Workbench for {rw_ticker}{alias_note} "
                    f"· {len(rw_bundle['candidates'])} candidate(s) ready. "
                    "Use the **Download** controls below to save the printable "
                    "brief and CSV artifacts — the server path "
                    f"`{rw_bundle['path']}` is not user-accessible on "
                    "Streamlit Cloud and is wiped on redeploy."
                )
            except Exception as exc:
                st.error(f"Workbench build failed: {exc}")

        show_ticker = _ss.get("mw_rw_last_ticker") or rw_ticker
        show_run = _ss.get("mw_rw_last_run_date") or rw_run_date
        if show_ticker and show_run:
            loaded_rw = workflow_ui.load_replacement_for_run(show_run, show_ticker)
            if loaded_rw is not None:
                summary = loaded_rw.get("summary", {}) or {}
                st.markdown(
                    f"**Workbench for {summary.get('ticker', show_ticker)}** "
                    f"— category `{summary.get('category') or 'unknown'}` "
                    f"({summary.get('category_source', '—')}) · "
                    f"{summary.get('candidate_count', 0)} candidate(s)"
                )
                if summary.get("alias_applied"):
                    st.info(
                        f"Share-class alias applied: "
                        f"`{summary.get('ticker')}` → "
                        f"`{summary.get('resolved_ticker')}`."
                    )

                # Surfaced inferred / applied discovery filters so the user
                # can verify the brief was scoped the way they expected.
                _inf_cat = summary.get("inferred_category")
                _inf_ft = summary.get("inferred_fund_type")
                _ft_used = summary.get("fund_type_filter_used")
                _ft_filter = summary.get("fund_type_filter")
                _cat_used = summary.get("category_filter_used")
                _filter_src = summary.get("filter_source") or "—"
                _applied_bits = []
                if _cat_used:
                    _applied_bits.append(
                        summary.get("category") or _inf_cat or "category"
                    )
                if _ft_used:
                    _applied_bits.append(_ft_filter or "type")
                if summary.get("candidate_universe_source") == "committee_list":
                    st.caption(
                        f"Discovery filters: **not forced** — committee "
                        f"list authoritative · inferred category "
                        f"`{_inf_cat or 'unknown'}`, inferred fund type "
                        f"`{_inf_ft or 'unknown'}`."
                    )
                else:
                    _applied_str = (
                        " + ".join(_applied_bits) if _applied_bits else "*none*"
                    )
                    st.caption(
                        f"Discovery filters applied: **{_applied_str}** "
                        f"(source: `{_filter_src}`) · inferred category "
                        f"`{_inf_cat or 'unknown'}`, inferred fund type "
                        f"`{_inf_ft or 'unknown'}`."
                    )
                cu_source = summary.get("candidate_universe_source")
                if cu_source == "committee_list":
                    st.success(
                        "Candidate universe: **uploaded committee "
                        f"candidate list** "
                        f"({summary.get('committee_list_size') or 0} "
                        "symbol(s)) — this brief uses only the names you "
                        "uploaded for committee review."
                    )
                    held_excl = (
                        summary.get(
                            "committee_list_excluded_held_symbols"
                        ) or []
                    )
                    if held_excl:
                        st.warning(
                            "Excluded as already-held model positions: "
                            + ", ".join("`" + s + "`" for s in held_excl)
                            + ". Toggle **Include already-held names** "
                            "below to keep them in the table."
                        )
                    missing_scored = (
                        summary.get(
                            "committee_list_missing_from_scored_universe"
                        ) or []
                    )
                    if missing_scored:
                        st.info(
                            "Committee-list names missing from the "
                            "scored universe (included as un-scored "
                            "rows): "
                            + ", ".join("`" + s + "`" for s in missing_scored)
                        )
                elif summary.get("restrict_to_candidate_exposures"):
                    st.caption(
                        "Candidate universe: **uploaded candidate "
                        "exposures** "
                        f"({summary.get('candidate_universe_size') or 0} "
                        "curated symbol(s)). "
                        + (
                            "Already-held model positions excluded."
                            if summary.get("exclude_already_held")
                            else "Already-held model positions retained."
                        )
                    )
                else:
                    st.caption(
                        "Candidate universe: **discovery mode** — full "
                        "scored universe in the same category. "
                        "Upload a committee candidate list above for a "
                        "staff-facing brief scoped to the names actually "
                        "under consideration. "
                        + (
                            "Already-held model positions excluded."
                            if summary.get("exclude_already_held")
                            else "Already-held model positions flagged but kept."
                        )
                    )
                fit_enabled = bool(summary.get("benchmark_fit_enabled"))
                if fit_enabled:
                    tab_prof, tab_cand, tab_fit, tab_drift, tab_brief = st.tabs([
                        "Current Holding Profile",
                        "Top Candidates",
                        "Benchmark-Fit Ranking",
                        "Current vs Benchmark",
                        "Brief",
                    ])
                else:
                    tab_prof, tab_cand, tab_brief = st.tabs(
                        ["Current Holding Profile", "Top Candidates", "Brief"]
                    )
                    tab_fit = tab_drift = None

                with tab_prof:
                    st.dataframe(
                        loaded_rw.get("current_profile", pd.DataFrame()),
                        use_container_width=True, hide_index=True,
                    )
                with tab_cand:
                    st.dataframe(
                        loaded_rw.get("candidates", pd.DataFrame()),
                        use_container_width=True, hide_index=True,
                    )
                if fit_enabled and tab_fit is not None:
                    with tab_fit:
                        bw = summary.get("benchmark_weights") or {}
                        if bw:
                            wstr = ", ".join(
                                f"{k} {v:.0%}" for k, v in bw.items()
                            )
                            st.caption(f"Benchmark weights: {wstr}")
                        st.markdown(
                            f"**Baseline sleeve fit:** "
                            f"{summary.get('baseline_fit_label', '—')} · "
                            f"total drift "
                            f"{summary.get('baseline_total_abs_drift', 0):.3f} · "
                            f"max bucket "
                            f"`{summary.get('baseline_max_drift_bucket') or '—'}` "
                            f"({summary.get('baseline_max_abs_drift', 0):.3f})"
                        )
                        st.markdown(
                            "**Best by FundScore:** "
                            f"`{summary.get('best_fundscore_candidate') or '—'}` · "
                            "**Best by benchmark fit:** "
                            f"`{summary.get('best_benchmark_fit_candidate') or '—'}` · "
                            "**Balanced:** "
                            f"`{summary.get('balanced_candidate') or '—'}`"
                        )
                        st.dataframe(
                            loaded_rw.get(
                                "benchmark_fit_candidates", pd.DataFrame(),
                            ),
                            use_container_width=True, hide_index=True,
                        )
                if fit_enabled and tab_drift is not None:
                    with tab_drift:
                        st.dataframe(
                            loaded_rw.get(
                                "current_vs_benchmark", pd.DataFrame(),
                            ),
                            use_container_width=True, hide_index=True,
                        )
                        rd = loaded_rw.get(
                            "replacement_delta", pd.DataFrame(),
                        )
                        if not rd.empty:
                            st.markdown(
                                "**After top benchmark-fit replacement:**"
                            )
                            st.dataframe(
                                rd,
                                use_container_width=True, hide_index=True,
                            )
                with tab_brief:
                    st.markdown(loaded_rw.get("brief_markdown", ""))

                # --- Downloads (Streamlit Cloud-friendly artifact access) ---
                from printable_brief import (
                    build_artifact_zip as _build_artifact_zip,
                    render_printable_brief_html as _render_printable_html,
                )

                st.markdown("#### Downloads")
                st.caption(
                    "Streamlit Cloud's run-archive directory is **ephemeral** "
                    "and not user-accessible. Save these files locally for "
                    "committee records — Quarto is **not** required for the "
                    "printable brief (it is only needed for the full monthly "
                    "packet)."
                )
                try:
                    _printable_html = _render_printable_html(
                        loaded_rw, run_date=show_run,
                    )
                except Exception as _exc:
                    _printable_html = None
                    st.error(f"Failed to render printable brief: {_exc}")

                _dl_cols = st.columns(3)
                _dl_idx = [0]

                def _next_dl_col():
                    col = _dl_cols[_dl_idx[0] % len(_dl_cols)]
                    _dl_idx[0] += 1
                    return col

                _dl_ticker = (
                    summary.get("ticker") or show_ticker or "REPLACEMENT"
                )

                if _printable_html:
                    with _next_dl_col():
                        st.download_button(
                            "⬇︎ Printable brief (HTML)",
                            data=_printable_html.encode("utf-8"),
                            file_name=f"{_dl_ticker}_printable_brief.html",
                            mime="text/html",
                            help=(
                                "Self-contained HTML — open and use the "
                                "browser's Print → Save as PDF for the "
                                "committee packet."
                            ),
                            key=f"mw_rw_dl_html_{show_run}_{_dl_ticker}",
                        )

                _md_brief = loaded_rw.get("brief_markdown") or ""
                if _md_brief:
                    with _next_dl_col():
                        st.download_button(
                            "⬇︎ Markdown brief",
                            data=_md_brief.encode("utf-8"),
                            file_name=f"{_dl_ticker}_replacement_brief.md",
                            mime="text/markdown",
                            key=f"mw_rw_dl_md_{show_run}_{_dl_ticker}",
                        )

                _cand_df = loaded_rw.get("candidates", pd.DataFrame())
                if isinstance(_cand_df, pd.DataFrame) and not _cand_df.empty:
                    with _next_dl_col():
                        st.download_button(
                            "⬇︎ Candidates (CSV)",
                            data=_cand_df.to_csv(index=False).encode("utf-8"),
                            file_name=(
                                f"{_dl_ticker}_replacement_candidates.csv"
                            ),
                            mime="text/csv",
                            key=f"mw_rw_dl_cand_{show_run}_{_dl_ticker}",
                        )

                _fit_df = loaded_rw.get(
                    "benchmark_fit_candidates", pd.DataFrame(),
                )
                if isinstance(_fit_df, pd.DataFrame) and not _fit_df.empty:
                    with _next_dl_col():
                        st.download_button(
                            "⬇︎ Benchmark-fit candidates (CSV)",
                            data=_fit_df.to_csv(index=False).encode("utf-8"),
                            file_name=(
                                f"{_dl_ticker}_benchmark_fit_candidates.csv"
                            ),
                            mime="text/csv",
                            key=f"mw_rw_dl_fit_{show_run}_{_dl_ticker}",
                        )

                _cb_df = loaded_rw.get("current_vs_benchmark", pd.DataFrame())
                if isinstance(_cb_df, pd.DataFrame) and not _cb_df.empty:
                    with _next_dl_col():
                        st.download_button(
                            "⬇︎ Current vs benchmark (CSV)",
                            data=_cb_df.to_csv(index=False).encode("utf-8"),
                            file_name=(
                                f"{_dl_ticker}_current_vs_benchmark_exposure.csv"
                            ),
                            mime="text/csv",
                            key=f"mw_rw_dl_cb_{show_run}_{_dl_ticker}",
                        )

                _rd_df = loaded_rw.get("replacement_delta", pd.DataFrame())
                if isinstance(_rd_df, pd.DataFrame) and not _rd_df.empty:
                    with _next_dl_col():
                        st.download_button(
                            "⬇︎ Replacement exposure delta (CSV)",
                            data=_rd_df.to_csv(index=False).encode("utf-8"),
                            file_name=(
                                f"{_dl_ticker}_replacement_exposure_delta.csv"
                            ),
                            mime="text/csv",
                            key=f"mw_rw_dl_rd_{show_run}_{_dl_ticker}",
                        )

                try:
                    _zip_bytes = _build_artifact_zip(
                        loaded_rw, html_brief=_printable_html,
                    )
                    with _next_dl_col():
                        st.download_button(
                            "⬇︎ All artifacts (ZIP)",
                            data=_zip_bytes,
                            file_name=f"{_dl_ticker}_replacement_workbench.zip",
                            mime="application/zip",
                            help=(
                                "Bundles the printable HTML, markdown brief, "
                                "summary JSON, and every non-empty CSV for "
                                "this run."
                            ),
                            key=f"mw_rw_dl_zip_{show_run}_{_dl_ticker}",
                        )
                except Exception as _exc:
                    st.warning(f"ZIP bundle unavailable: {_exc}")

    # ---- Step 5: Archive list + comparison ----
    st.markdown("### 5 · Archived Runs & Comparison")
    runs_available = workflow_ui.available_runs()
    if not runs_available:
        st.caption("No archived runs found.")
    else:
        st.write(f"**{len(runs_available)}** run(s) on disk:")
        st.code("\n".join(runs_available), language="text")

    if len(runs_available) >= 2:
        if st.button("Run Comparison (latest vs prior)", key="mw_btn_compare"):
            try:
                with st.spinner("Computing comparison…"):
                    comp = workflow_ui.maybe_compare()
                if comp is None:
                    st.warning("Not enough runs to compare.")
                else:
                    st.success(
                        f"Compared {comp['latest_date']} vs {comp['prior_date']}"
                    )
                    summ = comp.get("summary", {})
                    st.json(summ)
                    for name, df in comp["tables"].items():
                        if df is None or df.empty:
                            continue
                        with st.expander(f"{name} ({len(df):,} rows)"):
                            st.dataframe(df, use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error(f"Comparison failed: {exc}")
    else:
        st.caption("At least two archived runs are required to run a comparison.")

    # ---- Step 6: Excel audit export ----
    st.markdown("### 6 · Excel Audit Workbook")
    if runs_available:
        export_date = st.selectbox(
            "Export run date",
            options=list(reversed(runs_available)),
            index=0,
            key="mw_export_date",
        )
        if st.button("Build Audit Workbook", key="mw_btn_xlsx"):
            try:
                with st.spinner("Rendering Excel workbook…"):
                    fname, data = workflow_ui.build_audit_workbook_bytes(
                        run_date=export_date,
                    )
                st.session_state["mw_xlsx_bytes"] = data
                st.session_state["mw_xlsx_fname"] = fname
                st.success(f"Built {fname} ({len(data):,} bytes)")
            except Exception as exc:
                st.error(f"Workbook export failed: {exc}")

        if st.session_state.get("mw_xlsx_bytes"):
            st.download_button(
                "⬇ Download Audit Workbook (.xlsx)",
                data=st.session_state["mw_xlsx_bytes"],
                file_name=st.session_state["mw_xlsx_fname"],
                mime=(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
                key="mw_xlsx_download",
            )
    else:
        st.caption("Create a run archive above to enable the audit export.")

    # ---- Step 7: Monthly packet (Quarto) ----
    st.markdown("### 7 · Monthly Packet (Quarto)")
    packet_path = workflow_ui.find_packet_html()
    if packet_path:
        with open(packet_path, "rb") as fh:
            st.download_button(
                "⬇ Download Monthly Packet HTML",
                data=fh.read(),
                file_name=os.path.basename(packet_path),
                mime="text/html",
                key="mw_packet_download",
            )
        st.caption(f"Serving pre-rendered packet from `{packet_path}`.")
    else:
        st.caption(
            "No pre-rendered packet found. Render it from the project root with:"
        )
        st.code(
            "quarto render reports/monthly_packet/monthly_packet.qmd",
            language="bash",
        )


# ===========================================================================
# PAGE: Upload CSV
# ===========================================================================

elif page == "Upload CSV":
    st.markdown("## Upload CSV")
    st.markdown(
        "Upload an exported YCharts fund CSV to score your own universe. "
        "The file must contain the standard column headers (see README for details)."
    )

    uploaded = st.file_uploader("Choose a CSV file", type=["csv"])

    if uploaded is not None:
        try:
            raw_df = pd.read_csv(uploaded)
            st.markdown("### Preview (first 10 rows)")
            st.dataframe(raw_df.head(10), use_container_width=True)
            st.caption(f"{len(raw_df):,} rows · {len(raw_df.columns)} columns")

            if st.button("Score Funds", type="primary"):
                with st.spinner("Computing scores…"):
                    scored = score_funds(raw_df)
                    st.session_state["scored_df"] = scored
                st.success(f"Scored {len(scored):,} funds successfully!")

                # Summary
                valid = scored[scored[SCORE_COL].notna()]
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Avg Score", f"{valid[SCORE_COL].mean():.1f}")
                with c2:
                    st.metric("Strong", f"{(valid[BAND_COL]=='STRONG').sum():,}")
                with c3:
                    st.metric("Weak", f"{(valid[BAND_COL]=='WEAK').sum():,}")

                # Download
                csv_out = scored.to_csv(index=False).encode()
                st.download_button(
                    "⬇ Download Scored CSV",
                    data=csv_out,
                    file_name="scored_funds.csv",
                    mime="text/csv",
                )

                st.markdown("---")
                st.info("Results loaded into session — navigate to other pages to explore.")

        except Exception as e:
            st.error(f"Error reading file: {e}")

    else:
        # Show sample data info
        st.markdown("---")
        st.markdown("#### Sample Data")
        df = get_data()
        if not df.empty:
            st.caption(f"Using bundled sample data ({len(df):,} funds). Navigate to other pages to explore.")
            st.dataframe(df[[SYM_COL, NAME_COL, TYPE_COL, CAT_COL, SCORE_COL, BAND_COL]].head(20), use_container_width=True)
        else:
            st.warning("No sample data found. Please upload a CSV to get started.")
