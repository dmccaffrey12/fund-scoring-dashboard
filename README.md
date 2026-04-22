# FundScore Dashboard

A quantitative fund scoring system for portfolio managers. Scores mutual funds and ETFs on a 0-100 scale using within-category percentile rankings across two methodologies:

- **Passive System** — 10 metrics emphasizing cost and tracking accuracy (index funds)
- **Active System** — 16 metrics measuring manager skill and risk-adjusted returns

Built for a $700M+ AUM RIA serving retired households.

## Two Interfaces

### 🌐 React Web Dashboard (`/webapp`)
Production-grade dashboard built with React + Express + shadcn/ui. Committee-presentable with dark mode, interactive charts, and full scoring engine.

**Features:** Dashboard overview, batch scoring table, single fund lookup with radar chart, category analysis, model portfolio monitoring, CSV upload

**Run locally:**
```bash
cd webapp
npm install
npm run dev
```

### 📊 Streamlit App (`/streamlit`)
Lightweight analysis tool for day-to-day work. Runs in GitHub Codespaces.

**Run locally:**
```bash
cd streamlit
pip install -r requirements.txt
streamlit run app.py
```

## Scoring Methodology

### Within-Category Percentile Ranking
All metrics are ranked within Morningstar categories (Large Growth vs Large Growth peers, etc.).

### Pro-Rating for Missing Data
Funds with partial history are scored on available metrics only — the denominator adjusts so newer funds aren't penalized.

### Score Bands
| Score | Band | Meaning |
|-------|------|---------|
| ≥ 80 | 🟢 STRONG | Top-tier within category |
| 60-79.9 | 🟡 REVIEW | Average to above-average |
| < 60 | 🔴 WEAK | Below-average, investigate alternatives |

## Run Archive

Each scoring run can be archived to a dated folder so future month-over-month
comparisons (and the planned Excel 2019 audit export) have a stable substrate
to read from.

```bash
cd streamlit

# Create a dated archive from bundled data (defaults to today's date)
python run_archive.py create --notes "April committee packet"

# Use a specific date or custom inputs
python run_archive.py create \
    --run-date 2026-04-30 \
    --path-2025 /path/to/ycharts_export.csv \
    --path-2023 /path/to/scores_2023.csv

# Inspect available runs
python run_archive.py list
python run_archive.py show --latest
python run_archive.py show --run-date 2026-04-30
```

Each archive is laid out as:

```
streamlit/runs/
  latest.json                      # manifest pointing at the newest run
  YYYY-MM-DD/
    data/dual_score_table.csv      # canonical PR 3 output
    metadata/run_metadata.json     # run date, timestamp, input hashes, columns
    validation/validation_report.json  # row / band / quadrant counts, score ranges
```

`runs/latest.json` is a plain JSON manifest rather than a symlink so the
layout works on Windows and inside restricted CI runners. The `runs/`
directory is gitignored — archives are intended to live on the analyst's
machine or in a shared drive, not in the repo.

## Data Source
Export CSV from YCharts Fund Screener with the required metrics. See each app's documentation for the expected column format.

## Validation Targets
- SCHD (Passive): ~69.6
- OMCIX (Active): ~68.7
- Matches Excel workbook scoring within ±0.1 points

---
*Built with [Perplexity Computer](https://www.perplexity.ai/computer)*
