# FundScore — Streamlit Fund Scoring App

A production-quality Streamlit dashboard for scoring and analysing mutual funds and ETFs using a percentile-based ranking system within Morningstar peer categories.

---

## Quick Start (GitHub Codespaces)

### 1. Open in Codespaces

Click **Code → Open with Codespaces** in the GitHub repository, or open an existing Codespace and navigate to this directory.

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the app

```bash
streamlit run app.py
```

Streamlit will start on port **8501**. Codespaces will prompt you to open the forwarded port in your browser.

---

## Project Structure

```
fund-scoring-streamlit/
├── app.py                  # Main Streamlit application
├── scoring_engine.py       # Core percentile-based scoring engine
├── sample_data.csv         # Sample YCharts export (4,800+ funds)
├── requirements.txt        # Python dependencies
├── .streamlit/
│   └── config.toml         # Dark theme configuration
└── README.md               # This file
```

---

## Scoring Methodology

### Fund Type Detection
- **Passive** (Index Fund = True): Uses the passive 10-metric system
- **Active** (Index Fund = False): Uses the active 16-metric system

### Percentile Ranking
Each metric is ranked **within the fund's Morningstar category** (peer group), not across all funds:

- **"Higher is better"** metrics: `percentile = (peers with value ≤ this fund) / total peers`
- **"Lower is better"** metrics: `percentile = (peers with value ≥ this fund) / total peers`

Missing data is handled gracefully: weights for missing metrics are excluded from the denominator, so a fund with fewer data points is not penalised unfairly.

### Scoring Systems

**Passive (10 metrics, total weight 90 → normalized 0-100 by available weight)**

| Metric | Weight | Direction |
|--------|--------|-----------|
| Expense Ratio | 40 | Lower |
| Tracking Error (3Y) | 10 | Lower |
| Tracking Error (5Y) | 10 | Lower |
| Tracking Error (10Y) | 10 | Lower |
| R-Squared (5Y) | 5 | Higher |
| AUM | 6 | Higher |
| Downside (5Y) | 3 | Lower |
| Downside (10Y) | 2 | Lower |
| Max Drawdown (5Y) | 2 | Lower |
| Max Drawdown (10Y) | 2 | Lower |

**Active (16 metrics, 100 raw points)**

| Metric | Weight | Direction |
|--------|--------|-----------|
| Expense Ratio | 25 | Lower |
| Information Ratio (3Y) | 10 | Higher |
| Information Ratio (5Y) | 6 | Higher |
| Information Ratio (10Y) | 4 | Higher |
| Sortino Ratio (3Y) | 10 | Higher |
| Sortino Ratio (5Y) | 6 | Higher |
| Sortino Ratio (10Y) | 4 | Higher |
| Max Drawdown (5Y) | 7 | Lower |
| Max Drawdown (10Y) | 3 | Lower |
| Downside (5Y) | 7 | Lower |
| Downside (10Y) | 3 | Lower |
| 3Y Return | 1 | Higher |
| 5Y Return | 1 | Higher |
| 10Y Return | 2 | Higher |
| Upside (5Y) | 6 | Higher |
| Upside (10Y) | 5 | Higher |

### Score Bands
- **STRONG**: score ≥ 70
- **REVIEW**: 40 ≤ score < 70
- **WEAK**: score < 40

---

## CSV Format

The app expects a YCharts export with these exact column headers:

| Column | Description |
|--------|-------------|
| `Symbol` | Ticker symbol |
| `Name` | Fund name |
| `Index Fund` | True/False |
| `Category Name` | Morningstar category |
| `Net Expense Ratio` | As decimal (e.g. 0.001 = 0.1%) |
| `Tracking Error (vs Category) (3Y/5Y/10Y)` | |
| `R-Squared (vs Category) (5Y)` | |
| `Share Class Assets Under Management` | In USD |
| `Downside (vs Category) (5Y/10Y)` | |
| `Max Drawdown (5Y/10Y)` | |
| `Information Ratio (vs Category) (3Y/5Y/10Y)` | |
| `Historical Sortino (3Y/5Y/10Y)` | |
| `Upside (vs Category) (5Y/10Y)` | |
| `3/5/10 Year Total Returns (Daily)` | As decimal |

---

## App Pages

| Page | Description |
|------|-------------|
| **Dashboard** | KPI metrics, score distribution histogram, top category bar chart |
| **Batch Scores** | Filterable/searchable full fund table with CSV export |
| **Fund Lookup** | Ticker lookup with large score display, metrics table, radar chart |
| **Category Analysis** | Per-category distribution, scatter plot, ranked list |
| **Upload CSV** | Upload your own YCharts export, score it, and download results |

---

## Validation

Reference scores from the Excel workbook:

| Fund | Type | Expected Score |
|------|------|----------------|
| SCHD | Passive | ~69.6 |
| OMCIX | Active | ~68.7 |

To verify:

```python
import pandas as pd
from scoring_engine import score_funds

df = pd.read_csv('sample_data.csv')
scored = score_funds(df)

schd = scored[scored['Symbol'] == 'SCHD']
omcix = scored[scored['Symbol'] == 'OMCIX']

print(f"SCHD  Score: {schd['Score_Final'].values[0]:.1f}  (expected ~69.6, Passive)")
print(f"OMCIX Score: {omcix['Score_Final'].values[0]:.1f}  (expected ~68.7, Active)")
```

---

## Dark Theme

The app uses a custom dark theme configured in `.streamlit/config.toml`:

```toml
[theme]
primaryColor       = "#4F98A3"
backgroundColor    = "#171614"
secondaryBackgroundColor = "#1C1B19"
textColor          = "#CDCCCA"
```

---

## Dependencies

| Package | Version |
|---------|---------|
| streamlit | ≥1.30.0 |
| pandas | ≥2.0.0 |
| numpy | ≥1.24.0 |
| plotly | ≥5.18.0 |

---

## Dual-Score Table — Shared Data Contract

`dual_score_table.py` produces a single canonical DataFrame — one row per
fund — that joins the **2023 Combined System** (`scores_2023.csv`) with the
**2025 Split System** (scored live from a YCharts export). This is the
shared contract consumed by the Streamlit app, the Quarto monthly packet,
and the future Excel audit export.

### Usage

```python
from dual_score_table import build_dual_score_table

table = build_dual_score_table()           # uses bundled defaults
table = build_dual_score_table(how="outer")  # keep funds in either system
```

CLI:

```bash
python dual_score_table.py --out outputs/dual_score_table.csv
```

### Columns

| Column | Type | Notes |
|---|---|---|
| `Symbol` | str | Ticker — join key |
| `Name` | str | Prefers 2025 source, falls back to 2023 |
| `Category` | str | Morningstar category, same fallback rule |
| `Fund_Type` | str | `Passive` or `Active` (from 2025 engine) |
| `Score_2023_Final` | float | 2023 Combined System (0–100) |
| `Score_2025_Final` | float | 2025 system (0–100) |
| `Score_Gap` | float | `Score_2025_Final − Score_2023_Final` |
| `Rank_2023` / `Rank_2025` | Int | Dense rank, 1 = best |
| `Consensus_Rank` | Int | Dense rank on the mean of the two ranks |
| `Score_Band_2023` / `Score_Band_2025` | str | `STRONG` / `REVIEW` / `WEAK` (80 / 60) |
| `Quadrant` | str | `Q1_Both_Strong`, `Q2_Only_2025`, `Q3_Only_2023`, `Q4_Both_Weak` |
| `Data_Coverage_2023` | float | `Avail_Weight / 100` |
| `Data_Coverage_2025` | float | Share of metric weight backed by non-null values |
| `Primary_Driver` | str | Heuristic label on `Score_Gap` direction |
| `Action_Flag` | str | `LEAD`, `REVIEW`, `WATCH`, `DROP` |

Columns are omitted gracefully if the source data doesn't support them
(e.g. `Data_Coverage_2023` is `NaN` if `Avail_Weight` is absent).

### Smoke tests

```bash
python tests/test_dual_score_table.py
# or
pytest tests/test_dual_score_table.py
```

## Benchmark Fit / Portfolio Alignment

The Replacement Workbench can rank candidates by **drift vs a static
100/0 equity benchmark** in addition to FundScore. This answers the
question *"which replacement improves the lineup while preserving or
improving sector / stylebox alignment?"*.

### 100/0 equity sleeve as the base

The investment team treats the 100/0 model as the canonical equity
sleeve. Lower-risk models (90/10, 80/20, etc.) are scaled versions of
the same sleeve, so we maintain **one** set of equity-side benchmark
targets, not one per risk model. All drift math is computed against
that single sleeve.

### Default benchmark weights

| Symbol | Weight | Role |
|--------|--------|------|
| `SPYM` | 58%   | US large-cap core |
| `EFA`  | 24%   | Developed ex-US |
| `SPMD` | 6%    | US mid-cap |
| `SPSM` | 6%    | US small-cap |
| `EEM`  | 6%    | Emerging markets |

Defined in `streamlit/benchmark_fit.py` as `DEFAULT_BENCHMARK_WEIGHTS`
and editable in the Streamlit UI textarea (one `SYMBOL=weight` per
line). The weights should sum to ~1.00; the UI warns if they do not.

### Expected YCharts exposure export format

Wide CSV with one row per symbol and the following columns:

```
Symbol, Name,
Equity Stylebox Large Cap Value Exposure,
Equity Stylebox Large Cap Blend Exposure,
Equity Stylebox Large Cap Growth Exposure,
Equity Stylebox Mid Cap Value Exposure,
Equity Stylebox Mid Cap Blend Exposure,
Equity Stylebox Mid Cap Growth Exposure,
Equity Stylebox Small Cap Value Exposure,
Equity Stylebox Small Cap Blend Exposure,
Equity Stylebox Small Cap Growth Exposure,
Basic Materials Exposure, Consumer Cyclical Exposure,
Financial Services Exposure, Real Estate Exposure,
Communication Services Exposure, Energy Exposure,
Industrials Exposure, Technology Exposure,
Consumer Defensive Exposure, Healthcare Exposure,
Utilities Exposure
```

Values are decimals (0.20 = 20%). Each block (stylebox or sector) is
expected to sum to ~1.00 per fund; `exposure_intake.validate_exposures`
emits warnings when sums fall outside the configurable tolerance
(default ±0.05) and errors on missing / blank / duplicate symbols.

### Three uploads in Step 4c

1. **Model holdings exposures** — exposures for every ticker the 100/0
   model holds today.
2. **Benchmark constituents exposures** — exposures for the five
   benchmark ETFs above (or whichever weights you configure).
3. **Candidate ideas exposures** — exposures for the same-category
   candidate universe you are willing to consider.

A fourth optional upload is the **model holdings library** (CSV with
`Model_Name, Symbol, Target_Weight, Sleeve`) — without it the workbench
falls back to the repo-root `model_holdings_master_library_converted.csv`.
Only the `100/0` model rows are used for drift math.

### Drift metrics

For each stylebox and sector bucket *b*:

```
active[b] = weighted_actual[b] - weighted_benchmark[b]
```

Aggregates:

- `total_abs_drift` — sum of |active[b]| across all 20 buckets.
- `max_abs_drift` / `max_drift_bucket` — the single largest deviation.
- `stylebox_total_abs_drift` / `sector_total_abs_drift` — the same
  total split across the two axes.

Fit labels (tunable in `benchmark_fit.py`):

| Label | Total drift | Max bucket drift |
|-------|-------------|------------------|
| Strong Fit | ≤ 0.20 | ≤ 0.06 |
| Acceptable | ≤ 0.40 | ≤ 0.10 |
| Drift Risk | otherwise | otherwise |

### Replacement simulation

For a target ticker T at its model weight wT, simulate replacing T with
each candidate C by computing:

```
actual_after[b] = actual_before[b] - wT * exposure_T[b] + wT * exposure_C[b]
```

and re-running the drift math against the same benchmark. Candidates
are ranked ascending by `Total_Abs_Drift_After` (best fit first).

### Artifacts produced

Under `runs/<run-date>/replacement_workbench/<TICKER>/`:

- `replacement_candidates.csv` — same-category candidates with the dual
  2023 / 2025 score lens, plus (when fit layer ran) drift columns and
  the `Fit_Label` / `Fit_Rank`.
- `current_holding_profile.csv` — one-row profile for the current
  holding.
- `replacement_summary.json` — adds `baseline_fit_label`,
  `baseline_total_abs_drift`, `best_fundscore_candidate`,
  `best_benchmark_fit_candidate`, `balanced_candidate`, and the
  benchmark weights actually used.
- `replacement_brief.md` — committee-readable Markdown brief.
- `benchmark_fit_candidates.csv` *(only when fit layer runs)* — the
  full benchmark-fit ranking.
- `current_vs_benchmark_exposure.csv` *(only when fit layer runs)* —
  long-form per-bucket model vs benchmark exposures + active drift.
- `replacement_exposure_delta.csv` *(only when fit layer runs)* —
  per-bucket exposures after the **top benchmark-fit replacement**.

The dual-lens (2023 / 2025 / Consensus) ranking is **never** blended
away by the fit layer. The summary surfaces three picks side-by-side
(best by FundScore, best by fit, best balanced) so the committee can
weigh them.

### Printable brief & Streamlit Cloud downloads

`printable_brief.py` renders a self-contained HTML brief for one
replacement decision (no Quarto / pandoc required) and powers the
**Downloads** row beneath the workbench tabs. Streamlit Cloud's run
directory is ephemeral and not user-accessible, so the page exposes
`st.download_button` controls for:

- the printable HTML brief (browser-print → PDF for paper or committee
  packet),
- the Markdown brief,
- each non-empty CSV (candidates, benchmark-fit candidates,
  current-vs-benchmark exposures, replacement-exposure delta), and
- a one-click ZIP bundle of every available artifact.

The brief itself includes the current-holding summary, methodology,
top FundScore candidates, benchmark-fit candidates (when present),
headline picks (best FundScore / best fit / balanced), drift summary,
and a data-quality block that explicitly notes the ephemeral storage
caveat. Save the downloads locally — the server-side path under
`runs/<date>/replacement_workbench/<TICKER>/` is recreated on every
Streamlit Cloud redeploy and should not be treated as durable storage.
