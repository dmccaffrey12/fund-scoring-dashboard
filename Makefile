.PHONY: packet packet-latest packet-clean

# Render the monthly Quarto committee packet (HTML) against an archived run.
# Requires the quarto CLI and Python deps (see reports/monthly_packet/README.md).
#
# Examples:
#   make packet                                 # resolves via latest.json / newest dated folder
#   make packet RUN_DATE=2026-04-30             # pick a specific archive by date
#   make packet RUN_PATH=/abs/path/runs/2026-04-30
#   make packet OUT=/tmp/april_packet.html
packet:
	bash reports/monthly_packet/render.sh \
	  $(if $(RUN_PATH),--run-path $(RUN_PATH)) \
	  $(if $(RUN_DATE),--run-date $(RUN_DATE)) \
	  $(if $(RUNS_DIR),--runs-dir $(RUNS_DIR)) \
	  $(if $(OUT),--out $(OUT))

# Backwards-compatible alias.
packet-latest: packet

# Remove the rendered packet output (project-root default location).
packet-clean:
	rm -f reports/monthly_packet/monthly_packet.html
	rm -rf reports/monthly_packet/monthly_packet_files
	rm -rf reports/monthly_packet/.quarto
