# Monthly Fund Review — Quarto Packet

A single-HTML committee packet rendered from an **archived scoring run**
(produced by `streamlit/run_archive.py`). Self-contained output suitable for
emailing, archiving, or attaching to the monthly review cycle notes.

This is the consumer side of the run-archive / dual-score-table / run-comparison
pipeline. Nothing is computed from ad-hoc sample data — the packet always
reflects a specific dated run directory.

## Render engine & theme

The packet is rendered by **Quarto** with a custom theme (`fundscore.scss`
+ `fundscore.css`) that replaces Quarto's default Bootstrap look with a
committee-memo aesthetic: calm ivory background, serif body type, restrained
numbered sections, numeric-aligned committee tables, muted chart palette, and
a print/PDF media block.

- `fundscore.scss` — SCSS variables + rules layered on top of the `cosmo`
  base. Owns typography, spacing, section dividers, dataframe/table styling,
  TOC look, blockquote/placeholder treatment, and print overrides.
- `fundscore.css` — companion rules that don't compose cleanly in SCSS
  (numeric-column alignment, colophon banner styling, scroll containers).
- `monthly_packet.qmd` — sets `theme: [cosmo, fundscore.scss]`, registers a
  shared `PACKET_PALETTE` for matplotlib charts, and narrows the page to
  `body-width: 860px` for memo-like line length.

To change the committee-packet aesthetic (fonts, section colour, table
density, chart palette) edit those three files — no downstream tooling
needs to change.

## What's in the packet

1. **Executive Summary** — universe size, band mix, consensus leaders, MoM headline.
2. **Data Quality & Preflight** — row/coverage/band/quadrant counts from the
   run's `validation_report.json`; YCharts `intake_report.json` findings when present.
3. **Top 50 Consensus Ideas** — best of both lenses by `Consensus_Rank`.
4. **Top 50 by Performance Lens (2023)** — returns / alpha / capture view.
5. **Top 50 by Quality/Risk Lens (2025)** — information ratio / Sortino / tracking error / cost view.
6. **Disagreement List** — funds where the two lenses diverge by ≥ 10 points or by band.
7. **Dual-Lens Matrix** — scatter + 3×3 band matrix + quadrant counts.
8. **What Changed** — month-over-month movers, band / quadrant / action-flag
   changes, new/removed funds. Falls back to a clearly-labelled placeholder when
   no comparison bundle is present.
9. **Methodology Notes** — data sources, scoring systems, known limitations.

## Data inputs

The packet reads these artifacts from a single run directory:

```
streamlit/runs/YYYY-MM-DD/
  data/dual_score_table.csv                        (required)
  metadata/run_metadata.json                       (required)
  validation/validation_report.json                (optional)
  validation/intake_report.json                    (optional — YCharts preflight)
  comparison/prior_YYYY-MM-DD/
    summary.json
    score_movers.csv
    band_changes.csv
    quadrant_changes.csv
    action_flag_changes.csv
    new_funds.csv
    removed_funds.csv                              (optional — MoM comparison)
```

Every optional file is handled gracefully — if it's missing the
corresponding section renders a labelled placeholder.

### Run resolution order

The `.qmd` resolves which run to read via this waterfall:

1. `FUND_PACKET_RUN_PATH` — explicit absolute path to a run directory.
2. `FUND_PACKET_RUN_DATE` — `YYYY-MM-DD`, looked up under
   `FUND_PACKET_RUNS_DIR` (default `streamlit/runs/`).
3. `streamlit/runs/latest.json` manifest.
4. Lexicographic maximum of dated folders under `streamlit/runs/`.

`FUND_PACKET_RUNS_DIR` can also be exported to point at a shared-drive
archive root (anything with the same `YYYY-MM-DD/...` layout works).

## Prerequisites

### 1. Quarto CLI

Install Quarto (≥ 1.4) from <https://quarto.org/docs/get-started/>. The
binary is **not vendored** into the repo.

```bash
quarto --version
```

### 2. Python dependencies

Install Python deps into the same environment you use for the Streamlit app,
plus the reporting extras:

```bash
pip install -r streamlit/requirements.txt
pip install -r reports/monthly_packet/requirements.txt
```

`reports/monthly_packet/requirements.txt` covers `jupyter`, `matplotlib`,
`tabulate`, `nbformat` — the extras Quarto's Jupyter engine needs beyond
the Streamlit baseline.

## Creating an archive first

The packet requires at least one run archive. Typical monthly flow:

```bash
cd streamlit

# Create an archive from the current YCharts exports.
python run_archive.py create \
  --run-date 2026-04-30 \
  --path-2025 /path/to/ycharts_2025_export.csv \
  --path-2023 /path/to/ycharts_2023_export.csv \
  --notes "April committee packet" \
  --preflight warn

# (Optional) compute the month-over-month comparison against the prior run.
python run_comparison.py compare
```

## Rendering

### Default (resolves latest run)

```bash
make packet
# or
bash reports/monthly_packet/render.sh
# or
quarto render reports/monthly_packet/monthly_packet.qmd
```

### Specific run by date

```bash
make packet RUN_DATE=2026-04-30
# or
bash reports/monthly_packet/render.sh --run-date 2026-04-30
# or
FUND_PACKET_RUN_DATE=2026-04-30 quarto render reports/monthly_packet/monthly_packet.qmd
```

### Explicit absolute run path (e.g. off a shared drive)

```bash
make packet RUN_PATH=/shared/fund_scoring/runs/2026-04-30
# or
bash reports/monthly_packet/render.sh --run-path /shared/fund_scoring/runs/2026-04-30
```

### Custom output location

```bash
make packet OUT=/tmp/april_packet.html
# or
bash reports/monthly_packet/render.sh --run-date 2026-04-30 --out /tmp/april_packet.html
```

The default output HTML lands next to the `.qmd` file
(`reports/monthly_packet/monthly_packet.html`), gitignored and self-contained.

### Print / PDF

The theme ships print-friendly CSS: sections force page breaks at H1, the
TOC + code-fold chrome drop out, and tables avoid mid-row breaks where the
browser's paginator allows. To produce a PDF from the rendered HTML, open
the file in Chrome / Edge and print with "Background graphics" **on** so
the memo treatment of the executive-summary callout and banner reaches the
PDF. That keeps the rendered HTML self-contained (no PDF toolchain
dependency); the Quarto render already emits `embed-resources: true`.

If a Chromium-headless workflow is added in the future, a native PDF target
can be wired up via `quarto render --to pdf` with a LaTeX engine; this
repo deliberately keeps PDF out of the critical path.

## Refreshing for the next cycle

1. Produce a fresh run archive (`run_archive.py create ...`).
2. Optionally compute the comparison against the prior run
   (`run_comparison.py compare`).
3. Re-render: `make packet`.

No code changes are required for a normal month.

## Known limitations

- **Consensus rank is unweighted.** A production weighting may favour the
  forward-looking 2025 lens.
- **Top-50 tables are universe-wide.** Filter to the firm's approved list
  before committee distribution.
- **Intake preflight is optional.** If `intake_report.json` is absent the
  Data Quality section reports only the post-scoring validation counters.
