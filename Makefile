.PHONY: packet packet-clean

# Render the monthly Quarto committee packet (HTML).
# Requires the quarto CLI and Python deps (see reports/monthly_packet/README.md).
packet:
	quarto render reports/monthly_packet/monthly_packet.qmd

# Remove the rendered packet output.
packet-clean:
	rm -f reports/monthly_packet/monthly_packet.html
	rm -rf reports/monthly_packet/monthly_packet_files
