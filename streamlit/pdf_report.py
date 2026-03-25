"""
PDF Report Generation
=====================
Generate professional IC committee reports using fpdf2.
"""

import io
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from fpdf import FPDF, XPos, YPos

from scoring_engine import (
    ACTIVE_METRICS,
    CSV_COLUMNS,
    PASSIVE_METRICS,
    PASSIVE_RESCALE,
)
from score_explainer import (
    METRIC_LABELS,
    _get_fund_breakdown,
    explain_score,
    generate_category_narrative,
)

# ---------------------------------------------------------------------------
# Unicode safety helper
# ---------------------------------------------------------------------------

def _safe(text: str) -> str:
    """Replace non-latin-1 characters with ASCII equivalents for fpdf2 core fonts."""
    _MAP = {
        '\u2014': ' - ',  # em dash
        '\u2013': '-',    # en dash
        '\u2015': '-',    # horizontal bar
        '\u2265': '>=',   # >=
        '\u2264': '<=',   # <=
        '\u2019': "'",   # right single quote
        '\u2018': "'",   # left single quote
        '\u201c': '"',   # left double quote
        '\u201d': '"',   # right double quote
        '\u2026': '...',  # ellipsis
        '\u00b0': ' deg', # degree
        '\u2022': '-',    # bullet
        '\u00b7': '*',    # middle dot
        '\u2192': '->',   # right arrow
        '\u00e2': 'a',    # a-circumflex
    }
    result = []
    for ch in str(text):
        if ord(ch) < 128:
            result.append(ch)
        elif ch in _MAP:
            result.append(_MAP[ch])
        elif ord(ch) < 256:
            # Latin-1 range is fine
            result.append(ch)
        else:
            result.append('?')
    return ''.join(result)


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

NAVY = (15, 23, 42)        # #0f172a header bg
WHITE = (255, 255, 255)
LIGHT_GRAY = (245, 246, 248)
MID_GRAY = (180, 184, 190)
DARK_GRAY = (50, 55, 65)
GREEN = (22, 163, 74)      # STRONG
YELLOW = (202, 138, 4)     # REVIEW
RED = (185, 28, 28)        # WEAK
BLACK = (20, 20, 20)
TEAL = (15, 118, 135)      # accent

SCORE_BAND_COLORS = {
    "STRONG": GREEN,
    "REVIEW": YELLOW,
    "WEAK": RED,
}

SYM_COL = CSV_COLUMNS["symbol"]
NAME_COL = CSV_COLUMNS["name"]
CAT_COL = CSV_COLUMNS["category"]
ER_COL = CSV_COLUMNS["expense_ratio"]
SCORE_COL = "Score_Final"
BAND_COL = "Score_Band"
TYPE_COL = "Fund_Type"


# ---------------------------------------------------------------------------
# PDF class
# ---------------------------------------------------------------------------

class FundReport(FPDF):
    def __init__(self, title="Fund Scoring Report"):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.report_title = title
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(left=18, top=18, right=18)

    def cell(self, w=None, h=None, text="", border=0, ln="DEPRECATED", align="L",
             fill=False, link=None, center=False, markdown=False,
             new_x=XPos.RIGHT, new_y=YPos.TOP):
        return super().cell(w=w, h=h, text=_safe(text), border=border, align=align,
                            fill=fill, link=link, center=center, markdown=markdown,
                            new_x=new_x, new_y=new_y)

    def multi_cell(self, w, h=None, text="", border=0, align="J", fill=False,
                   split_only=False, link=None, ln="DEPRECATED", max_line_height=None,
                   markdown=False, print_sh=False, new_x=XPos.RIGHT, new_y=YPos.NEXT,
                   wrapmode="WORD", dry_run=False, center=False, padding=0):
        return super().multi_cell(w=w, h=h, text=_safe(text), border=border, align=align,
                                  fill=fill, link=link, split_only=split_only,
                                  max_line_height=max_line_height, markdown=markdown,
                                  print_sh=print_sh, new_x=new_x, new_y=new_y,
                                  wrapmode=wrapmode, dry_run=dry_run, center=center,
                                  padding=padding)

    # -----------------------------------------------------------------------
    # Header / Footer
    # -----------------------------------------------------------------------

    def header(self):
        if self.page_no() == 1:
            return  # Cover page handles its own layout
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(*MID_GRAY)
        self.cell(0, 6, self.report_title, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*MID_GRAY)
        self.line(18, self.get_y(), 192, self.get_y())
        self.ln(3)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MID_GRAY)
        date_str = datetime.now().strftime("%B %d, %Y")
        self.cell(0, 6, f"FundScore Report  ·  {date_str}  ·  Page {self.page_no()}", align="C")

    # -----------------------------------------------------------------------
    # Section utilities
    # -----------------------------------------------------------------------

    def section_title(self, text: str):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*NAVY)
        self.set_fill_color(*LIGHT_GRAY)
        self.cell(0, 8, text, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def kpi_row(self, items: list):
        """Render a row of KPI boxes. Each item is (label, value)."""
        col_w = (self.epw) / len(items)
        x_start = self.get_x()
        y_start = self.get_y()
        box_h = 18

        for label, value in items:
            self.set_xy(x_start, y_start)
            self.set_fill_color(*LIGHT_GRAY)
            self.set_draw_color(*MID_GRAY)
            self.rect(x_start, y_start, col_w - 2, box_h, style="FD")

            # Label
            self.set_xy(x_start + 2, y_start + 2)
            self.set_font("Helvetica", "", 7)
            self.set_text_color(*MID_GRAY)
            self.cell(col_w - 4, 5, str(label).upper(), align="L")

            # Value
            self.set_xy(x_start + 2, y_start + 7)
            self.set_font("Helvetica", "B", 11)
            self.set_text_color(*DARK_GRAY)
            self.cell(col_w - 4, 7, str(value), align="L")

            x_start += col_w

        self.set_xy(self.l_margin, y_start + box_h + 3)

    def band_badge(self, band: str, x, y, w=22, h=7):
        color = SCORE_BAND_COLORS.get(band, MID_GRAY)
        self.set_fill_color(*color)
        self.set_draw_color(*color)
        self.rect(x, y, w, h, style="F")
        self.set_xy(x, y + 1)
        self.set_font("Helvetica", "B", 7)
        self.set_text_color(*WHITE)
        self.cell(w, 5, band, align="C")
        self.set_text_color(*BLACK)

    def score_circle(self, score, band: str, x, y, r=14):
        """Draw a coloured circle with the score inside."""
        color = SCORE_BAND_COLORS.get(band, MID_GRAY)
        self.set_fill_color(*color)
        self.ellipse(x - r, y - r, r * 2, r * 2, style="F")
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*WHITE)
        score_str = f"{score:.1f}" if pd.notna(score) else "N/A"
        self.set_xy(x - r, y - 5)
        self.cell(r * 2, 10, score_str, align="C")
        self.set_text_color(*BLACK)

    # -----------------------------------------------------------------------
    # Table helpers
    # -----------------------------------------------------------------------

    def table_header(self, cols: list, widths: list):
        """Draw table header row with navy bg and white text."""
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 8)
        for col, w in zip(cols, widths):
            self.cell(w, 8, col, border=0, align="C", fill=True)
        self.ln()

    def table_row(self, values: list, widths: list, fill: bool = False, score_col_idx: int = -1, band_col_idx: int = -1):
        """Draw a single table data row."""
        if fill:
            self.set_fill_color(*LIGHT_GRAY)
        else:
            self.set_fill_color(*WHITE)
        self.set_text_color(*DARK_GRAY)
        self.set_font("Helvetica", "", 8)

        x0 = self.get_x()
        y0 = self.get_y()
        row_h = 7

        for i, (val, w) in enumerate(zip(values, widths)):
            cell_x = self.get_x()
            cell_y = self.get_y()

            if i == score_col_idx and isinstance(val, (int, float)) and not (isinstance(val, float) and np.isnan(val)):
                # Colour score text
                score_val = float(val)
                if score_val >= 80:
                    self.set_text_color(*GREEN)
                elif score_val >= 60:
                    self.set_text_color(*YELLOW)
                else:
                    self.set_text_color(*RED)
                self.cell(w, row_h, f"{score_val:.1f}", border=0, align="C", fill=fill)
                self.set_text_color(*DARK_GRAY)
            elif i == band_col_idx:
                # Draw band as coloured rectangle
                color = SCORE_BAND_COLORS.get(str(val), MID_GRAY)
                self.set_fill_color(*color)
                pad = 1
                self.rect(cell_x + pad, cell_y + 1.5, w - 2 * pad, row_h - 3, style="F")
                self.set_font("Helvetica", "B", 6.5)
                self.set_text_color(*WHITE)
                self.set_xy(cell_x, cell_y + 1)
                self.cell(w, row_h - 1, str(val), border=0, align="C", fill=False)
                self.set_text_color(*DARK_GRAY)
                self.set_font("Helvetica", "", 8)
                if fill:
                    self.set_fill_color(*LIGHT_GRAY)
                else:
                    self.set_fill_color(*WHITE)
            else:
                self.cell(w, row_h, str(val) if val is not None else " - ", border=0, align="C", fill=fill)

        self.ln()


# ---------------------------------------------------------------------------
# Cover Page
# ---------------------------------------------------------------------------

def _cover_page(pdf: FundReport, scored_df: pd.DataFrame, title: str):
    pdf.add_page()

    # Top bar
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, 210, 55, style="F")

    # Title
    pdf.set_xy(18, 14)
    pdf.set_font("Helvetica", "B", 26)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 12, title, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_xy(18, 30)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*MID_GRAY)
    date_str = datetime.now().strftime("%B %d, %Y")
    pdf.cell(0, 8, f"Generated: {date_str}", align="L")

    pdf.set_text_color(*BLACK)

    # KPI summary
    scored = scored_df[scored_df[SCORE_COL].notna()]
    n_total = len(scored_df)
    avg_score = scored[SCORE_COL].mean() if len(scored) > 0 else 0
    pct_strong = (scored[BAND_COL] == "STRONG").sum() / len(scored) * 100 if len(scored) > 0 else 0
    pct_weak = (scored[BAND_COL] == "WEAK").sum() / len(scored) * 100 if len(scored) > 0 else 0
    n_passive = (scored_df[TYPE_COL] == "Passive").sum()
    n_active = (scored_df[TYPE_COL] == "Active").sum()

    # Best / worst category
    cat_avg = (
        scored.groupby(CAT_COL)[SCORE_COL]
        .agg(["mean", "count"])
        .reset_index()
        .query("count >= 3")
    )
    best_cat = cat_avg.loc[cat_avg["mean"].idxmax(), CAT_COL] if not cat_avg.empty else " - "
    worst_cat = cat_avg.loc[cat_avg["mean"].idxmin(), CAT_COL] if not cat_avg.empty else " - "

    pdf.set_xy(18, 68)
    pdf.kpi_row([
        ("Total Funds", f"{n_total:,}"),
        ("Avg Score", f"{avg_score:.1f}"),
        ("Strong (>=80)", f"{pct_strong:.1f}%"),
        ("Weak (<60)", f"{pct_weak:.1f}%"),
    ])

    pdf.ln(4)
    pdf.kpi_row([
        ("Passive Funds", f"{n_passive:,}"),
        ("Active Funds", f"{n_active:,}"),
        ("Best Category", best_cat[:22] if len(best_cat) > 22 else best_cat),
        ("Worst Category", worst_cat[:22] if len(worst_cat) > 22 else worst_cat),
    ])

    # Scoring system summary box
    pdf.ln(8)
    pdf.set_fill_color(*LIGHT_GRAY)
    pdf.set_draw_color(*MID_GRAY)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, "Scoring System Overview", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*DARK_GRAY)
    overview = (
        "Funds are scored within their Morningstar category peer group using a percentile-based system. "
        "Passive (index) funds are scored on 10 metrics (expense ratio 40%, tracking error 30%, "
        "R-squared 5%, AUM 7%, downside/drawdown 9%), rescaled to a 100-point scale. "
        "Active funds are scored on 16 metrics (expense ratio 25%, information ratio 20%, "
        "Sortino ratio 20%, downside protection 20%, upside capture 11%, returns 4%). "
        "Score bands: STRONG >=80, REVIEW 60-79, WEAK <60."
    )
    pdf.multi_cell(0, 5.5, _safe(overview))

    # Band distribution bar
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, "Score Band Distribution", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    bar_w = pdf.epw
    n_strong_count = (scored[BAND_COL] == "STRONG").sum()
    n_review_count = (scored[BAND_COL] == "REVIEW").sum()
    n_weak_count = (scored[BAND_COL] == "WEAK").sum()
    n_scored = len(scored)

    x0 = pdf.get_x()
    y0 = pdf.get_y()
    bar_h = 10

    for band, count, color in [("STRONG", n_strong_count, GREEN), ("REVIEW", n_review_count, YELLOW), ("WEAK", n_weak_count, RED)]:
        frac = count / n_scored if n_scored > 0 else 0
        seg_w = bar_w * frac
        if seg_w < 0.5:
            continue
        pdf.set_fill_color(*color)
        pdf.rect(x0, y0, seg_w, bar_h, style="F")
        if seg_w > 12:
            pdf.set_xy(x0, y0 + 1)
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_text_color(*WHITE)
            pdf.cell(seg_w, 8, f"{frac*100:.0f}%", align="C")
        x0 += seg_w

    pdf.set_text_color(*BLACK)
    pdf.set_xy(pdf.l_margin, y0 + bar_h + 3)

    # Legend
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(*DARK_GRAY)
    for band, count, color in [("STRONG", n_strong_count, GREEN), ("REVIEW", n_review_count, YELLOW), ("WEAK", n_weak_count, RED)]:
        pdf.set_fill_color(*color)
        cur_x = pdf.get_x()
        cur_y = pdf.get_y()
        pdf.rect(cur_x, cur_y + 1, 5, 4, style="F")
        pdf.set_xy(cur_x + 6, cur_y)
        pdf.cell(40, 6, f"{band}: {count:,}")
    pdf.ln(8)


# ---------------------------------------------------------------------------
# Category Section
# ---------------------------------------------------------------------------

def _category_section(pdf: FundReport, scored_df: pd.DataFrame, category: str):
    pdf.add_page()
    pdf.section_title(f"Category: {category}")

    cat_df = scored_df[scored_df[CAT_COL] == category]
    scored_cat = cat_df[cat_df[SCORE_COL].notna()]

    n_total = len(cat_df)
    n_passive = (cat_df[TYPE_COL] == "Passive").sum()
    n_active = (cat_df[TYPE_COL] == "Active").sum()
    avg_score = scored_cat[SCORE_COL].mean() if len(scored_cat) > 0 else 0
    pct_strong = (scored_cat[BAND_COL] == "STRONG").sum() / len(scored_cat) * 100 if len(scored_cat) > 0 else 0

    # KPIs
    pdf.kpi_row([
        ("Total Funds", str(n_total)),
        ("Avg Score", f"{avg_score:.1f}"),
        ("Passive", str(n_passive)),
        ("Active", str(n_active)),
        ("% Strong", f"{pct_strong:.0f}%"),
    ])

    # Narrative
    narrative = generate_category_narrative(scored_df, category)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*DARK_GRAY)
    pdf.multi_cell(0, 5, _safe(narrative))
    pdf.ln(4)

    # Top 10 table
    top10 = (
        scored_cat[[SYM_COL, NAME_COL, SCORE_COL, BAND_COL, TYPE_COL, ER_COL]]
        .sort_values(SCORE_COL, ascending=False)
        .head(10)
    )

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, "Top 10 Funds", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    col_widths = [18, 62, 20, 22, 18, 26]
    headers = ["Symbol", "Name", "Score", "Band", "Type", "Expense Ratio"]
    pdf.table_header(headers, col_widths)

    for i, (_, row) in enumerate(top10.iterrows()):
        er = row.get(ER_COL)
        er_str = f"{er*100:.3f}%" if pd.notna(er) else " - "
        name_val = str(row.get(NAME_COL, ""))
        if len(name_val) > 38:
            name_val = name_val[:35] + "..."
        values = [
            str(row.get(SYM_COL, "")),
            name_val,
            row.get(SCORE_COL),
            str(row.get(BAND_COL, "")),
            str(row.get(TYPE_COL, "")),
            er_str,
        ]
        pdf.table_row(values, col_widths, fill=(i % 2 == 0), score_col_idx=2, band_col_idx=3)

    pdf.ln(4)


# ---------------------------------------------------------------------------
# Methodology Page
# ---------------------------------------------------------------------------

def _methodology_page(pdf: FundReport):
    pdf.add_page()
    pdf.section_title("Methodology")

    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*DARK_GRAY)
    intro = (
        "FundScore uses a percentile-based scoring system that evaluates each fund against its "
        "Morningstar category peers. Funds are split into Passive (index) and Active, each scored on a "
        "different set of metrics reflecting what matters most for that type of vehicle."
    )
    pdf.multi_cell(0, 5, _safe(intro))
    pdf.ln(4)

    # Passive weight table
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, "Passive System (10 metrics, rescaled ×1.111 to 100)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    p_headers = ["Metric", "Weight (raw pts)", "Direction"]
    p_widths = [90, 38, 38]
    pdf.table_header(p_headers, p_widths)
    for i, (key, weight, direction) in enumerate(PASSIVE_METRICS):
        pdf.table_row(
            [METRIC_LABELS.get(key, key), str(weight), direction.capitalize()],
            p_widths,
            fill=(i % 2 == 0),
        )
    pdf.ln(6)

    # Active weight table
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, "Active System (16 metrics, 100-point scale)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    a_headers = ["Metric", "Weight (raw pts)", "Direction"]
    a_widths = [90, 38, 38]
    pdf.table_header(a_headers, a_widths)
    for i, (key, weight, direction) in enumerate(ACTIVE_METRICS):
        pdf.table_row(
            [METRIC_LABELS.get(key, key), str(weight), direction.capitalize()],
            a_widths,
            fill=(i % 2 == 0),
        )

    pdf.ln(6)

    # Band definitions
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, "Score Band Definitions", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    b_headers = ["Band", "Score Range", "Interpretation"]
    b_widths = [30, 40, 96]
    pdf.table_header(b_headers, b_widths)
    bands_info = [
        ("STRONG", ">= 80", "Top performers  -  competitive cost, strong risk-adjusted returns"),
        ("REVIEW", "60 - 79", "Solid funds that may warrant deeper due diligence"),
        ("WEAK", "< 60", "Below-average performers  -  high costs or poor risk-adjusted returns"),
    ]
    for i, (band, rng, interp) in enumerate(bands_info):
        color = SCORE_BAND_COLORS.get(band, MID_GRAY)
        pdf.set_fill_color(*LIGHT_GRAY if i % 2 == 0 else WHITE)
        # Band cell coloured
        cur_x = pdf.get_x()
        cur_y = pdf.get_y()
        pdf.set_fill_color(*color)
        pdf.rect(cur_x, cur_y + 1, b_widths[0] - 2, 5, style="F")
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*WHITE)
        pdf.set_xy(cur_x, cur_y)
        pdf.cell(b_widths[0], 7, band, align="C")
        pdf.set_text_color(*DARK_GRAY)
        pdf.set_font("Helvetica", "", 8)
        if i % 2 == 0:
            pdf.set_fill_color(*LIGHT_GRAY)
        else:
            pdf.set_fill_color(*WHITE)
        pdf.cell(b_widths[1], 7, rng, align="C", fill=True)
        pdf.cell(b_widths[2], 7, interp, align="L", fill=True)
        pdf.ln()

    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(*MID_GRAY)
    pdf.multi_cell(
        0, 5,
        "Percentile ranks are computed within each Morningstar category. "
        "Funds with missing data for a metric have that metric excluded, and the score is "
        "rescaled based on available weight. A fund with all 10 passive metrics available "
        "receives the same maximum possible score as one with only 5 metrics  -  missing "
        "data does not penalize a fund."
    )


# ---------------------------------------------------------------------------
# Single Fund PDF
# ---------------------------------------------------------------------------

def _single_fund_page(pdf: FundReport, scored_df: pd.DataFrame, symbol: str):
    pdf.add_page()

    sym_col = CSV_COLUMNS["symbol"]
    row_match = scored_df[scored_df[sym_col] == symbol]
    if row_match.empty:
        pdf.section_title(f"Fund not found: {symbol}")
        return

    row = row_match.iloc[0]
    name = str(row.get(NAME_COL, symbol))
    category = str(row.get(CAT_COL, " - "))
    fund_type = str(row.get(TYPE_COL, " - "))
    score = row.get(SCORE_COL)
    band = str(row.get(BAND_COL, "WEAK"))
    er = row.get(ER_COL)
    er_str = f"{er*100:.3f}%" if pd.notna(er) else " - "

    # Header block
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, 210, 45, style="F")

    pdf.set_xy(18, 10)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 10, f"{symbol}  -  {name[:45]}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_xy(18, 23)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MID_GRAY)
    pdf.cell(80, 7, f"Category: {category}")
    pdf.cell(60, 7, f"Type: {fund_type}")
    pdf.cell(50, 7, f"Expense Ratio: {er_str}")

    pdf.set_text_color(*BLACK)
    pdf.set_xy(18, 56)

    # Score circle + KPIs
    band_color = SCORE_BAND_COLORS.get(band, MID_GRAY)

    # Score box
    pdf.set_fill_color(*band_color)
    pdf.rect(18, 56, 38, 28, style="F")
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*WHITE)
    score_str = f"{score:.1f}" if pd.notna(score) else "N/A"
    pdf.set_xy(18, 61)
    pdf.cell(38, 12, score_str, align="C")
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(18, 74)
    pdf.cell(38, 7, band, align="C")

    pdf.set_text_color(*BLACK)

    # Category rank context
    cat_peers = scored_df[scored_df[CAT_COL] == category][SCORE_COL].dropna()
    if len(cat_peers) > 0 and pd.notna(score):
        rank = int((cat_peers < score).sum()) + 1
        total_cat = len(cat_peers)
        pct_rank = round((cat_peers <= score).sum() / total_cat * 100)
        cat_avg = cat_peers.mean()
    else:
        rank = total_cat = pct_rank = None
        cat_avg = None

    x_kpi = 62
    pdf.set_xy(x_kpi, 56)
    kpi_items = [
        ("Category Rank", f"#{rank} of {total_cat}" if rank else " - "),
        ("Category Pctile", f"{pct_rank}th" if pct_rank else " - "),
        ("Category Avg", f"{cat_avg:.1f}" if cat_avg else " - "),
        ("Expense Ratio", er_str),
    ]
    kpi_w = (pdf.epw - 44) / len(kpi_items)
    for label, value in kpi_items:
        box_x = x_kpi
        pdf.set_fill_color(*LIGHT_GRAY)
        pdf.set_draw_color(*MID_GRAY)
        pdf.rect(box_x, 56, kpi_w - 2, 28, style="FD")
        pdf.set_xy(box_x + 2, 58)
        pdf.set_font("Helvetica", "", 6.5)
        pdf.set_text_color(*MID_GRAY)
        pdf.cell(kpi_w - 4, 5, label.upper(), align="L")
        pdf.set_xy(box_x + 2, 65)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*DARK_GRAY)
        pdf.cell(kpi_w - 4, 7, str(value), align="L")
        x_kpi += kpi_w

    pdf.set_xy(18, 92)
    pdf.ln(4)

    # Score explanation narrative
    explanation = explain_score(scored_df, symbol)
    if "error" not in explanation:
        pdf.section_title("Score Explanation")

        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*DARK_GRAY)
        pdf.multi_cell(0, 5, _safe(explanation.get("summary", "")))
        pdf.ln(2)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*DARK_GRAY)
        pdf.multi_cell(0, 5, _safe(explanation.get("fund_type_note", "")))
        pdf.ln(4)

        # Strengths
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(*GREEN)
        pdf.cell(0, 6, "Top Contributors (Strengths)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        for s in explanation.get("strengths", []):
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*DARK_GRAY)
            pdf.cell(0, 5, f"  {s['metric']}   -   {s['percentile']:.0f}th percentile  |  +{s['contribution_points']:.1f} pts", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(0, 5, f"    {s['sentence']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

        # Weaknesses
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(*RED)
        pdf.cell(0, 6, "Bottom Contributors (Weaknesses)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        for w in explanation.get("weaknesses", []):
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*DARK_GRAY)
            pdf.cell(0, 5, f"  {w['metric']}   -   {w['percentile']:.0f}th percentile  |  {w['contribution_points']:.1f} pts", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(0, 5, f"    {w['sentence']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)

        # Coverage
        cov = explanation.get("data_coverage", {})
        pdf.set_font("Helvetica", "I", 7.5)
        pdf.set_text_color(*MID_GRAY)
        missing_str = ", ".join(cov.get("missing", [])) if cov.get("missing") else "none"
        pdf.cell(0, 5, f"Data coverage: {cov.get('pct', 0):.0f}% ({cov.get('metrics_with_data', 0)}/{cov.get('total_metrics', 0)} metrics). Missing: {missing_str}.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)

    # Component percentile table
    breakdown_result = _get_fund_breakdown(scored_df, symbol)
    if isinstance(breakdown_result, tuple):
        breakdown, _ = breakdown_result
        if breakdown:
            pdf.section_title("Component Percentile Breakdown")
            t_headers = ["Metric", "Raw Value", "Percentile", "Weight", "Contribution"]
            t_widths = [60, 30, 28, 22, 26]
            pdf.table_header(t_headers, t_widths)
            sorted_items = sorted(breakdown.items(), key=lambda x: x[1]["contribution"], reverse=True)
            for i, (key, info) in enumerate(sorted_items):
                raw = info["raw_value"]
                # Format raw value
                if key == "expense_ratio":
                    raw_str = f"{raw*100:.3f}%" if pd.notna(raw) else " - "
                elif key in ("returns_3y", "returns_5y", "returns_10y"):
                    raw_str = f"{raw*100:.2f}%" if pd.notna(raw) else " - "
                elif key == "aum":
                    if pd.notna(raw):
                        raw_str = f"${raw/1e9:.2f}B" if raw >= 1e9 else f"${raw/1e6:.0f}M"
                    else:
                        raw_str = " - "
                else:
                    raw_str = f"{raw:.4f}" if pd.notna(raw) else " - "

                pdf.table_row(
                    [
                        METRIC_LABELS.get(key, key),
                        raw_str,
                        f"{info['percentile']:.0f}th",
                        str(info["weight"]),
                        f"{info['contribution']:.2f}",
                    ],
                    t_widths,
                    fill=(i % 2 == 0),
                )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_report(
    scored_df: pd.DataFrame,
    categories: Optional[list] = None,
    title: str = "Fund Scoring Report",
) -> bytes:
    """
    Generate a full PDF report.

    Parameters
    ----------
    scored_df  : Scored DataFrame
    categories : List of category names to include. If None, uses top 10 by fund count.
    title      : Report title

    Returns
    -------
    PDF as bytes
    """
    if categories is None:
        top_cats = (
            scored_df[CAT_COL].value_counts()
            .head(10)
            .index.tolist()
        )
        categories = top_cats

    pdf = FundReport(title=title)
    _cover_page(pdf, scored_df, title)

    for cat in categories:
        if cat in scored_df[CAT_COL].values:
            _category_section(pdf, scored_df, cat)

    _methodology_page(pdf)

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def generate_single_fund_report(scored_df: pd.DataFrame, symbol: str) -> bytes:
    """
    Generate a single-fund PDF report.

    Parameters
    ----------
    scored_df : Scored DataFrame
    symbol    : Ticker symbol

    Returns
    -------
    PDF as bytes
    """
    title = f"Fund Report: {symbol}"
    pdf = FundReport(title=title)
    _single_fund_page(pdf, scored_df, symbol)
    _methodology_page(pdf)

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()
