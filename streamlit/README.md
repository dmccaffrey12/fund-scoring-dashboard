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

**Passive (10 metrics, 90 raw points → rescaled ×1.111)**

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
