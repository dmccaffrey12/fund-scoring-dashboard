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

## Data Source
Export CSV from YCharts Fund Screener with the required metrics. See each app's documentation for the expected column format.

## Validation Targets
- SCHD (Passive): ~69.6
- OMCIX (Active): ~68.7
- Matches Excel workbook scoring within ±0.1 points

---
*Built with [Perplexity Computer](https://www.perplexity.ai/computer)*
