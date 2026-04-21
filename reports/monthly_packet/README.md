# Monthly Fund Review — Quarto Packet (Prototype)

A lightweight, non-PowerBI committee packet rendered from the repo's bundled
fund data. Produces a single self-contained HTML file suitable for emailing
or archiving alongside the monthly review cycle.

## What's in the packet

1. **Executive Summary** — universe size, band mix, consensus leaders.
2. **Top 50 Consensus Ideas** — funds ranked by the average of the 2023 and 2025 scores (only present if both lenses are available).
3. **Top 50 by Performance Lens (2023)** — backwards-looking returns / alpha / capture view.
4. **Top 50 by Quality / Risk Lens (2025)** — current information-ratio / Sortino / tracking-error / cost view.
5. **What Changed** — uses a historical archive if present, otherwise falls back to cross-system deltas.
6. **Dual-Lens Matrix** — scatter + 3×3 band matrix.
7. **Methodology Notes** — data sources, scoring systems, known limitations.

## Data inputs

The report reads the bundled sample files under `streamlit/`:

| File | Used for | Required? |
|------|----------|-----------|
| `streamlit/sample_data.csv` | 2025 Quality/Risk scores (live scored via `scoring_engine.py`) | Needed for 2025 / Consensus / Matrix |
| `streamlit/scores_2023.csv` | Pre-computed 2023 Performance scores | Needed for 2023 / Consensus / Matrix |
| `streamlit/history.csv` *(optional)* | Monthly archive for MoM deltas | Optional |

If either file is missing the corresponding section falls back to a clearly
labelled placeholder, so the packet always renders.

## Prerequisites

### 1. Quarto CLI

Install Quarto (≥ 1.4) from <https://quarto.org/docs/get-started/>. The
binary is **not vendored** into the repo.

```bash
quarto --version
```

### 2. Python dependencies

The report uses the Jupyter engine. Install Python deps into the same
environment you use for the Streamlit app, plus the reporting extras:

```bash
pip install -r streamlit/requirements.txt
pip install -r reports/monthly_packet/requirements.txt
```

`reports/monthly_packet/requirements.txt` covers `jupyter`, `matplotlib`,
`tabulate`, and `nbformat` — the extras Quarto needs beyond the Streamlit
app's baseline.

## Rendering

From the **repo root**:

```bash
make packet
```

or directly:

```bash
quarto render reports/monthly_packet/monthly_packet.qmd
```

or with the convenience script:

```bash
bash reports/monthly_packet/render.sh
```

The output HTML lands next to the `.qmd` file:

```
reports/monthly_packet/monthly_packet.html
```

It is a single self-contained file (`embed-resources: true`) — safe to email
or archive.

## Refreshing for the next cycle

1. Drop the latest YCharts export over `streamlit/sample_data.csv` (same column names as the current file).
2. If a new 2023-style score file is published, replace `streamlit/scores_2023.csv`.
3. Re-run `make packet`.

No code changes are required for a normal month.

## Known limitations (prototype)

- No share-class de-duplication yet.
- No historical MoM view — the *What Changed* section currently uses a cross-system delta proxy.
- Consensus ranking is an unweighted average; production may want to weight the 2025 lens higher.
- Top-50 tables are across the full universe — should be filtered to the firm's approved list before committee distribution.

These are tracked in the `# Known Limitations` section of the `.qmd` itself.
