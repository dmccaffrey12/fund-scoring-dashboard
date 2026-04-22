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

## Run Comparison (Month-over-Month "What Changed")

The old "What Changed" panel compared the 2023 and 2025 systems within a
single snapshot — a cross-system diff, not a time diff. `run_comparison.py`
replaces that proxy with a true month-over-month comparison: it joins two
archived runs on `Symbol` and emits one bundle of change tables plus a
JSON summary.

```bash
cd streamlit

# Latest vs the run immediately before it.
python run_comparison.py compare

# Compare two specific run dates.
python run_comparison.py compare \
    --latest-date 2026-04-30 \
    --prior-date 2026-03-31

# Cap to the 25 biggest movers per metric and skip writing files.
python run_comparison.py compare --top-n 25 --dry-run
```

Output lands under the latest run's folder so it travels with the archive:

```
streamlit/runs/<latest>/comparison/prior_<prior>/
    score_movers.csv           # long-format: Symbol, Metric, Value_Prior, Value_Latest, Delta, Abs_Delta
    band_changes.csv           # Score_Band_2023 / Score_Band_2025 transitions
    quadrant_changes.csv       # Quadrant transitions
    action_flag_changes.csv    # Action_Flag transitions
    new_funds.csv              # funds in latest but not prior
    removed_funds.csv          # funds in prior but not latest
    summary.json               # counts + run dates for a glanceable diff
```

If fewer than two runs exist the CLI exits with a clear error rather than
silently emitting an empty comparison. The module is importable from
Streamlit, Quarto, and Excel-export code paths — no UI is wired up yet.

```python
from run_comparison import run_comparison

result, paths = run_comparison()          # latest vs prior, persisted
result, _ = run_comparison(write=False)   # in-memory only
```

## Data Source
Export CSV from YCharts Fund Screener with the required metrics. See each app's documentation for the expected column format.

## YCharts Intake Validator

`streamlit/ycharts_intake.py` validates raw YCharts CSV exports **before** they feed the scoring engine or a run archive. It understands both the 29-column `2025` export and the 28-column `2023` export.

It checks:
- Required columns present
- `Symbol` column — no blanks, duplicates flagged
- Critical numeric columns parse as numbers (errors)
- Non-critical numeric columns parse (warnings)
- `Index Fund` (2025 only) parses as True/False
- Null rate per critical column vs a configurable threshold
- Joinability by `Symbol` when both files are provided

Findings carry severity `error` / `warning` / `info` and the report includes a `failed` flag (true if any error).

**CLI — single file:**
```bash
python streamlit/ycharts_intake.py --path-2025 data/2025_export.csv
python streamlit/ycharts_intake.py --path-2023 data/2023_export.csv
```

**CLI — both files + JSON artifact:**
```bash
python streamlit/ycharts_intake.py \
    --path-2025 data/2025_export.csv \
    --path-2023 data/2023_export.csv \
    --json-out intake_report.json
```

Exits non-zero on failure, so it can gate a CI step.

**Library — library preflight before `run_archive.create_run_archive`:**
```python
from ycharts_intake import preflight_for_archive
preflight_for_archive("data/2025.csv", "data/2023.csv", strict=True)
```

**Integrated preflight (new `--preflight` flag on `run_archive create`):**
```bash
python streamlit/run_archive.py create \
    --path-2025 data/2025.csv --path-2023 data/2023.csv \
    --preflight strict
```
When enabled, the full intake report is persisted to `validation/intake_report.json` inside the run folder and referenced from `run_metadata.json`.

## Excel 2019 Audit Workbook

`streamlit/excel_audit_export.py` turns any archived run into a single
`.xlsx` audit workbook that opens cleanly in **Excel 2019**. It uses only
legacy Excel features — no `XLOOKUP`, `LET`, `FILTER`, `SORT`, `UNIQUE`,
or `SEQUENCE`. Every number is precomputed, so there are no dynamic-array
formulas that would spill or break on older Excel.

```bash
cd streamlit

# Export the latest archived run (default output under runs/<date>/reports/).
python excel_audit_export.py export

# Export a specific run date to an explicit path.
python excel_audit_export.py export \
    --run-date 2026-04-30 \
    --out /tmp/fundscore_april.xlsx

# Skip the month-over-month comparison sheets even when present.
python excel_audit_export.py export --no-comparison
```

The default output location is:

```
streamlit/runs/<run-date>/reports/fundscore_audit_workbook.xlsx
```

Sheets included:

| Sheet | Contents |
|-------|----------|
| `README_Runbook` | Generation metadata, run date, input hashes, row / band / quadrant / action counts, sheet index. |
| `Methodology` | Scoring rubric, band and quadrant thresholds, Excel compatibility notes. |
| `Data_Quality` | Row / joined / missing counts, score & coverage summaries, band / quadrant / fund-type counters. |
| `Scored_Funds` | The full canonical dual-score table (one row per fund). |
| `Top_50_2023` / `Top_50_2025` / `Top_50_Consensus` | Top-50 cuts by each score / consensus rank. |
| `Disagreement_List` | Funds where 2023 and 2025 systems disagree (|Score_Gap| ≥ 10 or differing bands). |
| `What_Changed` *(if comparison exists)* | Headline month-over-month metrics, sourced from `run_comparison`. |
| `Score_Movers` / `Band_Changes` / `Quadrant_Changes` / `Action_Flag_Changes` / `New_Funds` / `Removed_Funds` *(if comparison exists)* | Detailed change tables carried over from the comparison bundle. |

STRONG / REVIEW / WEAK band cells are conditionally shaded (green /
yellow / red) and every dataset is a native Excel Table so sorting and
filtering work without a macro.

```python
from run_archive import load_latest_run
from excel_audit_export import build_audit_workbook

run = load_latest_run()
build_audit_workbook(run=run, out_path="/tmp/fundscore_audit.xlsx")
```

## Validation Targets
- SCHD (Passive): ~69.6
- OMCIX (Active): ~68.7
- Matches Excel workbook scoring within ±0.1 points

---
*Built with [Perplexity Computer](https://www.perplexity.ai/computer)*
