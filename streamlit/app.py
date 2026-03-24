"""
FundScore — Streamlit Fund Scoring App
=======================================
Multi-page analysis tool for portfolio managers.

Run:  streamlit run app.py
"""

import io
import os

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
# Session state helpers
# ---------------------------------------------------------------------------

SAMPLE_PATH = os.path.join(os.path.dirname(__file__), "sample_data.csv")


@st.cache_data(show_spinner="Scoring funds…")
def get_scored_data(path: str) -> pd.DataFrame:
    return load_and_score(path)


def get_data() -> pd.DataFrame:
    """Return scored DataFrame — either from uploaded file or sample data."""
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
    if score >= 70:
        return "score-strong"
    if score >= 40:
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


# ---------------------------------------------------------------------------
# Sidebar Navigation
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown('<div class="sidebar-brand">⬡ FundScore</div>', unsafe_allow_html=True)
    page = st.radio(
        "Navigation",
        ["Dashboard", "Batch Scores", "Fund Lookup", "Category Analysis", "Upload CSV"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    df = get_data()
    if not df.empty:
        st.caption(f"**{len(df):,}** funds loaded")
        n_passive = (df[TYPE_COL] == "Passive").sum()
        n_active = (df[TYPE_COL] == "Active").sum()
        st.caption(f"Passive: {n_passive:,}  ·  Active: {n_active:,}")
    else:
        st.caption("No data loaded")
    st.markdown("---")
    st.caption("FundScore · Portfolio Analytics")


# ===========================================================================
# PAGE: Dashboard
# ===========================================================================

if page == "Dashboard":
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

    # KPI Row
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card("Total Funds", f"{total:,}"), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("Average Score", f"{avg_score:.1f}", "out of 100"), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("Strong (≥70)", f"{pct_strong:.1f}%"), unsafe_allow_html=True)
    with c4:
        st.markdown(kpi_card("Weak (<40)", f"{pct_weak:.1f}%"), unsafe_allow_html=True)

    st.markdown("---")

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown('<div class="section-header">Score Distribution</div>', unsafe_allow_html=True)
        # Histogram by fund type
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
        fig_hist.add_vline(x=70, line_dash="dash", line_color="#4ade80", annotation_text="Strong", annotation_position="top right")
        fig_hist.add_vline(x=40, line_dash="dash", line_color="#f87171", annotation_text="Weak", annotation_position="top right")
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


# ===========================================================================
# PAGE: Batch Scores
# ===========================================================================

elif page == "Batch Scores":
    st.markdown("## Batch Scores")
    df = get_data()

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

    # Format
    if CSV_COLUMNS["expense_ratio"] in table.columns:
        table[CSV_COLUMNS["expense_ratio"]] = (table[CSV_COLUMNS["expense_ratio"]] * 100).round(3).astype(str) + "%"
    if CSV_COLUMNS["aum"] in table.columns:
        table[CSV_COLUMNS["aum"]] = table[CSV_COLUMNS["aum"]].apply(
            lambda x: f"${x/1e9:.2f}B" if pd.notna(x) and x >= 1e9 else (f"${x/1e6:.0f}M" if pd.notna(x) else "—")
        )
    if SCORE_COL in table.columns:
        table[SCORE_COL] = table[SCORE_COL].apply(lambda x: round(x, 1) if pd.notna(x) else None)
    table = table.rename(columns={SCORE_COL: "Score", BAND_COL: "Band"})

    # Colour the score column
    def style_score(val):
        if pd.isna(val):
            return ""
        if val >= 70:
            return "color: #4ade80; font-weight: 700"
        if val >= 40:
            return "color: #fbbf24; font-weight: 700"
        return "color: #f87171; font-weight: 700"

    st.dataframe(
        table.style.applymap(style_score, subset=["Score"]),
        use_container_width=True,
        height=520,
    )

    # CSV export
    csv_bytes = filtered[show_cols].to_csv(index=False).encode()
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

    if df.empty:
        st.warning("No data available. Upload a CSV on the **Upload CSV** page.")
        st.stop()

    ticker_input = st.text_input("Enter ticker symbol", placeholder="e.g. SCHD", max_chars=10)

    if not ticker_input:
        st.info("Enter a ticker symbol above to look up a fund.")
        st.stop()

    symbol = ticker_input.strip().upper()
    match = df[df[SYM_COL] == symbol]

    if match.empty:
        st.error(f"No fund found for ticker **{symbol}**.")
        st.stop()

    row = match.iloc[0]
    score = row.get(SCORE_COL)
    band = row.get(BAND_COL, "WEAK")
    fund_type = row.get(TYPE_COL, "Unknown")
    cat = row.get(CAT_COL, "—")
    name = row.get(NAME_COL, symbol)

    # Large score display
    color_map = {"STRONG": "#4ade80", "REVIEW": "#fbbf24", "WEAK": "#f87171"}
    score_color = color_map.get(band, "#CDCCCA")

    st.markdown(
        f"""
        <div style="background:#1C1B19; border:1px solid #2a2927; border-radius:10px;
                    padding:28px 32px; margin-bottom:24px; display:flex; align-items:center; gap:40px;">
            <div>
                <div style="font-size:0.72rem; letter-spacing:0.1em; text-transform:uppercase;
                            color:#7a7875; margin-bottom:4px;">Score</div>
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

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown('<div class="section-header">Key Metrics</div>', unsafe_allow_html=True)

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
            # Shorten long labels
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
                    name=symbol,
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
    st.markdown('<div class="section-header">Category Rank</div>', unsafe_allow_html=True)
    cat_peers = df[df[CAT_COL] == cat][SCORE_COL].dropna()
    if len(cat_peers) > 0:
        rank = (cat_peers < score).sum() + 1
        total_cat = len(cat_peers)
        pct_rank = (cat_peers <= score).sum() / total_cat * 100
        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            st.metric("Rank in Category", f"#{rank} of {total_cat}")
        with rc2:
            st.metric("Category Percentile", f"{pct_rank:.0f}th")
        with rc3:
            st.metric("Category Avg Score", f"{cat_peers.mean():.1f}")


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
        fig_hist.add_vline(x=70, line_dash="dash", line_color="#4ade80")
        fig_hist.add_vline(x=40, line_dash="dash", line_color="#f87171")
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
              .applymap(lambda v: "color: #4ade80; font-weight:700" if isinstance(v, (int, float)) and v >= 70 else
                                  ("color: #fbbf24; font-weight:700" if isinstance(v, (int, float)) and v >= 40 else
                                   ("color: #f87171" if isinstance(v, (int, float)) else "")), subset=["Score"])
              .applymap(style_band, subset=["Band"]),
        use_container_width=True,
        height=480,
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
