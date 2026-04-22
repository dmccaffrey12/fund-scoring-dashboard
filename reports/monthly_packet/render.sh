#!/usr/bin/env bash
# Render the monthly Quarto packet against an archived scoring run.
#
# Usage:
#   bash reports/monthly_packet/render.sh
#   bash reports/monthly_packet/render.sh --run-path /abs/path/to/streamlit/runs/2026-04-30
#   bash reports/monthly_packet/render.sh --run-date 2026-04-30
#   bash reports/monthly_packet/render.sh --runs-dir /shared/fund_scoring/runs --run-date 2026-04-30
#   bash reports/monthly_packet/render.sh --out /tmp/april_packet.html
#
# Environment variables (preferred by the .qmd at render time):
#   FUND_PACKET_RUN_PATH   — absolute path to a run directory
#   FUND_PACKET_RUN_DATE   — YYYY-MM-DD (looked up under FUND_PACKET_RUNS_DIR)
#   FUND_PACKET_RUNS_DIR   — parent directory (default: streamlit/runs)
#
# Defaults (no flags): resolve via latest.json manifest, then newest dated folder.
#
# Requires `quarto` on PATH and the Python deps from
#   streamlit/requirements.txt + reports/monthly_packet/requirements.txt
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

RUN_PATH=""
RUN_DATE=""
RUNS_DIR=""
OUT_PATH=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-path)    RUN_PATH="$2"; shift 2 ;;
    --run-date)    RUN_DATE="$2"; shift 2 ;;
    --runs-dir)    RUNS_DIR="$2"; shift 2 ;;
    --out)         OUT_PATH="$2"; shift 2 ;;
    --help|-h)
      grep -E '^# ' "$0" | sed -E 's/^# ?//'
      exit 0
      ;;
    *)
      EXTRA_ARGS+=("$1"); shift ;;
  esac
done

if ! command -v quarto >/dev/null 2>&1; then
  echo "error: quarto CLI not found on PATH." >&2
  echo "Install from https://quarto.org/docs/get-started/ and re-run." >&2
  exit 1
fi

if [[ -n "${RUN_PATH}" ]]; then
  export FUND_PACKET_RUN_PATH="${RUN_PATH}"
fi
if [[ -n "${RUN_DATE}" ]]; then
  export FUND_PACKET_RUN_DATE="${RUN_DATE}"
fi
if [[ -n "${RUNS_DIR}" ]]; then
  export FUND_PACKET_RUNS_DIR="${RUNS_DIR}"
fi

cd "${REPO_ROOT}"

QMD="reports/monthly_packet/monthly_packet.qmd"
if [[ -n "${OUT_PATH}" ]]; then
  exec quarto render "${QMD}" --output "${OUT_PATH}" "${EXTRA_ARGS[@]}"
else
  exec quarto render "${QMD}" "${EXTRA_ARGS[@]}"
fi
