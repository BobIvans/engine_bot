#!/usr/bin/env bash
set -euo pipefail

# Remove Python bytecode artifacts that should never appear in release zips.
find . -type d -name '__pycache__' -prune -exec rm -rf {} +
find . -type f -name '*.pyc' -delete

echo "Cleaned __pycache__/ and *.pyc"
