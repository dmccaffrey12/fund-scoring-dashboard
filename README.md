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

### Deterministic Output
Two runs built from the same inputs are guaranteed to produce byte-identical
dual-score tables — same rows, same column order, same values — so the
month-over-month comparison is empty when nothing has actually changed.
Concretely:

- Within-category percentile ranks are computed with pure pandas groupby +
  vectorised compares (no random or environment-dependent state).
- All output sorts use `kind="stable"` and an explicit `Symbol` tie-break
  so ties in `Consensus_Rank`, `Score_Final`, or Top-N score don't reorder
  between runs.
- YCharts occasionally lists the same ticker under two Morningstar
  categories (mid-period reclassifications, share-class quirks). The
  dual-score table collapses those to a single row per `Symbol` by taking
  the best-scoring duplicate on each side — deterministically, via a
  stable sort on score (desc), category (asc), and original row index.
  Duplicate `Symbol` values are forbidden in the one-row-per-fund contract
  because the month-over-month merge would otherwise produce a cartesian
  product of spurious deltas.

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

# `--path-2023` accepts either a pre-scored file (with a `Score_2023` column)
# OR a raw YCharts 2023 export — in the latter case `Score_2023` is computed
# on the fly using the same 15-metric weighting defined in
# `scoring_engine.SYSTEM_2023_METRICS`.

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
| `Model_Summary` / `Model_Holdings` / `Model_Review_List` / `Research_Candidates` / `Replacement_Candidates` *(if the model-holdings overlay exists)* | Committee overlay artifacts — see the **Model Holdings Overlay** section below. |

STRONG / REVIEW / WEAK band cells are conditionally shaded (green /
yellow / red) and every dataset is a native Excel Table so sorting and
filtering work without a macro.

```python
from run_archive import load_latest_run
from excel_audit_export import build_audit_workbook

run = load_latest_run()
build_audit_workbook(run=run, out_path="/tmp/fundscore_audit.xlsx")
```

## Model Holdings Overlay

`streamlit/model_holdings_overlay.py` joins current model portfolio
holdings against an archived dual-score table and emits committee-review
artifacts. The overlay is **a lens on top of the scored fund universe —
not part of the scoring methodology.** The 2023 and 2025 scores remain
separately reviewable so committee members can see where the two systems
agree and where they disagree.

### Expected CSV schema

Required columns:

| Column | Type | Notes |
|--------|------|-------|
| `Model_Name`   | str   | Free-text model label (e.g. "Moderate Growth"). |
| `Symbol`       | str   | Ticker; join key against the dual-score table. |
| `Target_Weight`| numeric or `"NN%"` | Percent or fractional. Per-model totals should sum to ~100%. |

Optional columns (preserved on the scorecard output if provided):
`Fund_Name`, `Sleeve`, `Status`, `Internal_Category`, `Notes`.

### Intake validation

```bash
cd streamlit

# Structure-only validation.
python model_holdings_intake.py --path my_models.csv

# Validate + report coverage against an archived dual-score table.
python model_holdings_intake.py \
    --path my_models.csv \
    --dual-score-table runs/2026-04-30/data/dual_score_table.csv
```

Surfaces errors (missing required columns, duplicate `Model_Name+Symbol`
pairs, unparseable weights, blank symbols) and warnings (per-model total
weights outside ±2% of 100%, low universe coverage).

### Overlay outputs

Artifacts are persisted under `runs/YYYY-MM-DD/model_holdings/`:

| File | Contents |
|------|----------|
| `model_holdings_scorecard.csv` | One row per holding joined to the dual scores, plus an `Overlay_Action` flag (see below). |
| `model_summary.csv` | One row per model with target-weighted 2023 / 2025 scores, coverage, and band / quadrant / action weight shares. |
| `current_holdings_review.csv` | Weak links — every holding that is *not* High Conviction, sorted by priority (replacement first). |
| `research_candidates.csv` | Top-scoring unheld funds (STRONG in at least one system), ranked by Consensus_Rank. |
| `replacement_candidates.csv` | Same-category replacement suggestions for each weak/weak current holding (top 3 per category). |
| `overlay_metadata.json` | Action-flag counts, model count, universe size. |

### Overlay action flags

`Overlay_Action` on the scorecard combines the 2023 and 2025 score bands
without collapsing their disagreement:

| Flag | When |
|------|------|
| `High_Conviction_Hold` | Held and STRONG in **both** systems. |
| `Performance_Led_Hold_Review_Quality` | Held, STRONG in 2023 but weaker in 2025 — performance track record is there, quality/risk story is not. |
| `Quality_Led_Hold_Review_Patience` | Held, STRONG in 2025 but weaker in 2023 — quality metrics look good, performance track record hasn't caught up. |
| `Replacement_Candidate` | Held but WEAK in either system — committee attention warranted. |
| `Review_Missing_Score` | Held but not in the scored fund universe (ticker change, share-class quirk, or legitimately unscored). |
| `Research_Candidate` | Not held today but scores STRONG in at least one system — surfaced on `research_candidates.csv`. |

### Share-class alias reconciliation

YCharts' duplicate-removal step keeps a single representative per fund, so a
model may record one share class (e.g. `PRBLX`) while the scored universe
contains another (e.g. `PRILX`). The overlay applies an alias layer before
joining so the committee-facing `Symbol` in the model library is preserved
while the score join happens against a reconciled ticker.

- **Default map** (`streamlit/config/symbol_aliases.csv`, also baked into
  `symbol_aliases.DEFAULT_ALIASES`): `PRBLX -> PRILX`, `GSTKX -> GSIKX`,
  `PONPX -> PIMIX`, `FECMX -> FEMKX`.
- **Extend without code changes** by editing that CSV — required columns are
  `Original_Symbol`, `Scoring_Symbol`; `Reason` is free-text for audit.
- **Override from the CLI** via `--alias-csv path/to/extra.csv`; entries in
  the extra CSV merge on top of the defaults.
- **Override from library code** by passing `alias_map=...` to
  `build_model_overlay` or `validate_model_holdings_*`.

The scorecard carries **both** `Symbol` (original, committee-facing) and
`Scoring_Symbol` (resolved, used for the join) along with an `Alias_Applied`
flag. `replacement_candidates.csv` surfaces `Current_Scoring_Symbol` alongside
`Current_Symbol`. Intake coverage reporting counts alias-applied rows
separately from still-unscored symbols, and the overlay metadata records
every `Original -> Scoring` pair that fired.

### CLI / library flow

```python
from model_holdings_overlay import build_model_overlay, write_overlay
from run_archive import load_run, run_overlay_dir
from symbol_aliases import load_default_aliases
import pandas as pd

run = load_run("2026-04-30")
holdings = pd.read_csv("my_models.csv")
result = build_model_overlay(
    holdings, run["table"],
    alias_map=load_default_aliases(),   # omit to use defaults automatically
)
write_overlay(result, run_overlay_dir("streamlit/runs", "2026-04-30"))
```

In the Streamlit **Monthly Workflow** page, the overlay upload appears as
*step 4b* after the run archive has been created: upload the holdings
CSV, run validation, build the overlay, and view **Model Stack-Up**,
**Current Holdings Review**, **Weak Links**, and **Top Candidates Not
Used** tabs. The subsequent Excel audit workbook automatically picks up
the overlay artifacts and adds the five `Model_*` / `Research_*` /
`Replacement_*` sheets.

## Replacement Workbench (per-ticker research)

`streamlit/replacement_workbench.py` is the one-off research companion to
the overlay: the overlay scans every holding in every model and emits a
packet-wide short list; the workbench answers **"if this single holding
isn't acceptable, what should replace it?"** for one ticker at a time.

The two are deliberately separate — the monthly Quarto packet and Excel
audit workbook still run off the overlay. The workbench is a focused
committee-prep tool for when a portfolio manager already knows which
holding they want to reconsider and needs a short, ranked same-category
candidate list with both the 2023 and 2025 systems visible side-by-side.

### What it does

Given a run archive and a current-holding ticker, it:

1. Resolves share-class aliases (e.g. `PRBLX` → `PRILX`) so the
   committee-facing ticker stays intact while the join lands on the scored
   representative.
2. Pulls the current holding's profile from the dual-score table (plus
   `Model_Name` / `Target_Weight_Pct` / `Overlay_Action` from the overlay
   scorecard if one has been generated).
3. Detects category from the scored universe, with an explicit
   `--category` override for tickers that aren't scored.
4. Filters the universe to **same-category candidates**, drops the
   current holding, and annotates (or optionally excludes) funds already
   held by any model.
5. Ranks candidates by `Consensus_Rank` (ascending, best first) with
   stable tie-breakers on 2025 score / 2023 score / Symbol. The 2023 and
   2025 scores, ranks, and bands are preserved on every row — the
   workbench never blends disagreement into one number. A plain-English
   `Reason_Label` summarises the fit (Consensus / Performance-led /
   Quality-led / Mixed / Weak).

### CLI

```bash
cd streamlit

# Latest run, default top-10, default alias map (PRBLX -> PRILX).
python replacement_workbench.py build --ticker PRBLX

# Specific run + larger short list, exclude candidates already held.
python replacement_workbench.py build \
    --run-date 2026-04-30 \
    --ticker PRBLX \
    --top-n 15 \
    --exclude-held

# Force a category override (useful when the ticker isn't in the universe).
python replacement_workbench.py build \
    --ticker SOMEFUND \
    --category "Large Blend"
```

### Artifact layout

Each run gets a per-ticker subfolder under its archive:

```
streamlit/runs/<run-date>/replacement_workbench/<TICKER>/
    replacement_candidates.csv     # ranked short list, dual-lens columns
    current_holding_profile.csv    # one row describing the current holding
    replacement_summary.json       # provenance (category source, counts, etc.)
    replacement_brief.md           # human-readable Markdown brief
    # Optional benchmark-fit artifacts (only when exposure files are supplied)
    benchmark_fit_candidates.csv          # candidates ranked by drift
    current_vs_benchmark_exposure.csv     # per-bucket model vs benchmark
    replacement_exposure_delta.csv        # exposures after top fit replacement
```

### Committee candidate list (optional, recommended for committee briefs)

The replacement workbench accepts an **authoritative candidate list** —
a small CSV of names the committee actually wants discussed for a given
replacement decision. When supplied it overrides same-category discovery
so the staff-facing short list and printable brief contain only those
symbols (plus any held-passive sleeves the user explicitly opts to
include).

**Schema** — one column is required (the symbol). Headers are matched
case-insensitively and any of the following are accepted:
`Symbol`, `Ticker`, `Fund Symbol`, `Candidate Symbol`. Optional metadata
columns are preserved when present:

| Column | Notes |
|--------|-------|
| `Name` / `Fund Name` | Display name. Wins over the exposure-CSV name and the scored-universe name. |
| `Active_Passive` / `Active/Passive` | Free text — passed through. |
| `Fund_Type` / `Fund Type` | Free text — passed through. |
| `Category` / `Morningstar Category` | Free text — passed through. |
| `Notes` / `Note` | Free text — passed through. |
| `Rationale` | Free text — passed through. |

Unknown columns survive the round-trip so user-supplied annotations are
not lost. Symbols are upper-cased and stripped; blank rows and duplicate
symbols are dropped (first occurrence wins).

**Universe priority** — when both a candidate list and a candidate
exposure CSV are uploaded, the candidate list wins for the universe and
display names; the exposure CSV continues to drive benchmark-fit metrics
for any of those symbols it covers. With no committee list, candidate
exposures define the curated universe; with neither, the brief falls
back to **discovery mode** (same-category scored universe), which the
banner labels explicitly.

**Already-held symbols** — by default the workbench excludes any
committee-list entry that is already a model holding (e.g. SPYM-style
passive sleeves) and surfaces them in
`summary["committee_list_excluded_held_symbols"]` so they are visible,
not silently dropped. Toggle `exclude_already_held=False` (or the
"Include already-held names" UI control) to keep them in the table —
they appear with `Already_Held=True` and the curated display name.

**Symbols missing from the scored universe** still appear in the
candidate table as un-scored rows so the committee sees the full set
they uploaded; they are listed in
`summary["committee_list_missing_from_scored_universe"]` and tagged
`Scored_In_Universe=False` with a clear `Reason_Label`.

A downloadable **template CSV** is offered next to the upload widget
in §4c of the Monthly Workflow page (`candidate_list_template_csv()`
in code).

### Benchmark fit / portfolio alignment (optional)

When the user uploads three YCharts exposure exports (model holdings,
benchmark constituents, candidate ideas) plus the holdings library, the
workbench layers a **portfolio-alignment** view on top of FundScore:

- Treats the **100/0 equity model** as the canonical equity sleeve
  (lower-risk models are scaled versions of it, so we maintain one set
  of equity targets, not one per risk model).
- Compares the model's weighted stylebox + sector exposures to a
  static 100/0 equity benchmark. Default weights: **SPYM 58%,
  EFA 24%, SPMD 6%, SPSM 6%, EEM 6%** (editable in the UI / in
  `benchmark_fit.DEFAULT_BENCHMARK_WEIGHTS`).
- Simulates replacing the target ticker at its 100/0 weight with each
  candidate, computing total absolute drift and max bucket drift before
  and after, plus a **Strong Fit / Acceptable / Drift Risk** label.
- Surfaces three picks in `replacement_summary.json`:
  `best_fundscore_candidate`, `best_benchmark_fit_candidate`, and
  `balanced_candidate` (combined Consensus_Rank + Fit_Rank). The
  dual-lens (2023 / 2025 / Consensus) ranking is preserved alongside.

See `streamlit/README.md` for the expected exposure-export column list,
fit thresholds, and how drift math is computed.

### Library

```python
from replacement_workbench import run_replacement_for_run

bundle = run_replacement_for_run(
    run_date="2026-04-30",
    ticker="PRBLX",
    top_n=10,
)
bundle["candidates"]          # ranked same-category short list
bundle["current_profile"]     # single-row DataFrame
bundle["brief_markdown"]      # Markdown string
bundle["paths"]               # dict of persisted artifact paths
```

### Streamlit UI

On the **Monthly Workflow** page the workbench is **step 4c**, directly
below the overlay. It picks up the run that the overlay was generated
against (or the latest run), pre-selects any model holding as the
"current holding" (with `PRBLX` preselected when present), lets you
override the category or the top-N, toggle exclude-held, and renders
three tabs: **Current Holding Profile**, **Top Candidates**, and the
**Brief**. Share-class aliases are surfaced in a banner when they fire.

### Printable brief & downloads (Streamlit Cloud)

After a workbench build the page exposes a **Downloads** row beneath
the tabs. Streamlit Cloud's run-archive directory (e.g.
`/mount/src/.../runs/<date>/replacement_workbench/<TICKER>/`) is
ephemeral and **not user-accessible** — anyone reviewing or printing
the brief should pull the files from these download buttons:

| Button | What it gives you |
|--------|-------------------|
| **Printable brief (HTML)** | Self-contained HTML with print CSS — open it and use the browser's *Print → Save as PDF* for paper-or-PDF committee review. Includes current-holding summary, methodology, top FundScore candidates, benchmark-fit candidates, headline picks, drift summary, data-quality notes, and the ephemeral-storage caveat. |
| **Markdown brief** | Same content as the on-page Brief tab. |
| **Candidates / Benchmark-fit / Current-vs-benchmark / Replacement-delta CSVs** | Each artifact appears only when non-empty for the run. |
| **All artifacts (ZIP)** | One-click bundle of every available artifact above. |

The printable brief is rendered entirely in-process — **Quarto is not
required** for the replacement brief. Quarto remains optional for the
full monthly committee packet (`reports/monthly_packet`); install it
locally if you need that packet, but you can run the replacement
workbench end-to-end on Streamlit Cloud without it.

### How it differs from the overlay and the Quarto packet

| Tool | Scope | When to use |
|------|-------|-------------|
| Overlay (`model_holdings_overlay`) | Every holding in every model | Monthly committee prep — flags weak links packet-wide |
| Quarto / Excel packet | Dual-score table + overlay artifacts | Durable monthly record |
| **Replacement Workbench** | **One ticker at a time** | **"I need to replace PRBLX — give me a short list"** |

## Validation Targets
- OMCIX (Active): ~68.7
- Both Active and Passive scores are bounded to 0-100 by available-weight normalization
- Matches Excel workbook scoring within ±0.1 points

---
*Built with [Perplexity Computer](https://www.perplexity.ai/computer)*
