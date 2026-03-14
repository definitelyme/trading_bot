#!/bin/bash
# Opens an SSH tunnel to the VPS and forwards the Freqtrade Web UI to localhost:8080.
# Run on your Mac: ./scripts/serve.sh
# Then open: http://localhost:8080 in your browser
# The tunnel stays open as long as this terminal window is open.

set -euo pipefail

VPS_IP="178.104.33.92"

echo "Opening SSH tunnel to $VPS_IP..."
echo "Web UI will be available at: http://localhost:8080"
echo "Press Ctrl+C to close the tunnel."
echo ""

ssh -N -L 8080:localhost:8080 deploy@"$VPS_IP"
