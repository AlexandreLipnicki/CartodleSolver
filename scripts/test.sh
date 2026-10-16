#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run build
.venv/bin/python scripts/test-automatic-ui.py
node scripts/test-history-images.mjs
