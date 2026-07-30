#!/bin/bash
# ==========================================================================
# CLOUDFLARE PAGES BUILD HOOK
# Runs the python RSS generator to compile rss.xml on deploy.
# ==========================================================================
set -e

echo "-> Starting Cloudflare Pages build step..."
python3 generate_rss.py
echo "-> Build step completed successfully."
