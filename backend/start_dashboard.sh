#!/usr/bin/env bash
# start_dashboard.sh — launch the Market Pulse Intelligence Streamlit dashboard.
#
# Usage (from any directory):
#   bash /path/to/trem-news/backend/start_dashboard.sh
#
# All critical server flags are passed explicitly so the script works
# regardless of whether .streamlit/config.toml is found, and regardless
# of which Python / virtual-environment is active.
#
# Why these flags are required in GitHub Codespaces
# ──────────────────────────────────────────────────
# --server.address=0.0.0.0
#     Bind to all interfaces so the Codespaces container network can
#     reach the process (default 'localhost' is unreachable externally).
#
# --server.enableCORS=false
#     Disable Streamlit's same-origin CORS guard so the Codespaces proxy
#     (which rewrites the Host header) can forward requests successfully.
#
# --server.enableXsrfProtection=false
#     Disable XSRF token validation.  Streamlit validates the Origin
#     header; Codespaces sends requests from *.app.github.dev ≠ localhost,
#     so every request would be silently rejected → HTTP 502.
#
# --server.headless=true
#     Suppress the "open browser" prompt and allow the process to start
#     without a display server.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Kill any process already bound to port 8501 to avoid "address in use" errors.
if command -v fuser >/dev/null 2>&1; then
    fuser -k 8501/tcp 2>/dev/null || true
elif command -v lsof >/dev/null 2>&1; then
    lsof -ti tcp:8501 | xargs -r kill -9 2>/dev/null || true
fi

echo ""
echo "  Market Pulse Intelligence — starting dashboard"
echo "  Port   : 8501"
echo "  Python : $(python3 --version 2>&1)"
echo "  Config : $(pwd)/.streamlit/config.toml"
echo ""

exec streamlit run dashboard.py \
    --server.address=0.0.0.0 \
    --server.port=8501 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --browser.gatherUsageStats=false
