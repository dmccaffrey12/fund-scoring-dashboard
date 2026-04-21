#!/usr/bin/env bash
# Render the monthly Quarto packet.
#
# Usage: bash reports/monthly_packet/render.sh
#
# Requires `quarto` on PATH and the Python deps from
#   streamlit/requirements.txt + reports/monthly_packet/requirements.txt
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if ! command -v quarto >/dev/null 2>&1; then
  echo "error: quarto CLI not found on PATH."
  echo "Install from https://quarto.org/docs/get-started/ and re-run."
  exit 1
fi

cd "${REPO_ROOT}"
exec quarto render reports/monthly_packet/monthly_packet.qmd "$@"
