#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
API_DIR="$ROOT_DIR/api"
PYTHON="$API_DIR/.venv/bin/python"

cd "$API_DIR"
"$PYTHON" scripts/garmin_sync.py --daily-only --days-back "${GARMIN_SYNC_DAYS_BACK:-2}"
"$PYTHON" scripts/garmin_sync.py --calendar-only
"$PYTHON" scripts/garmin_sync.py --peloton --days-back "${PELOTON_SYNC_DAYS_BACK:-7}"
