#!/bin/bash
# ==========================================================================
# CLOUDFLARE PAGES BUILD HOOK
# Runs the python RSS generator to compile rss.xml on deploy.
# ==========================================================================
set -e

echo "-> Starting Cloudflare Pages build step..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/generate_rss.py"
echo "-> Build step completed successfully."
