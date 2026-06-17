#!/usr/bin/env bash
# start_dashboard.sh — launch the Market Pulse Intelligence Streamlit dashboard.
#
# Usage (from the trem-news/backend directory):
#   bash start_dashboard.sh
#
# The required server flags are already set in .streamlit/config.toml.
# This script just ensures you're in the right directory before starting.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting Market Pulse Intelligence dashboard on port 8501..."
echo "In GitHub Codespaces: open the PORTS tab and click the 8501 forwarded address."
echo ""

exec streamlit run dashboard.py
