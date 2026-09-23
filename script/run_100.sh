#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export USER_COUNT=100
export RUN_ID="${RUN_ID:-run_100_$(date -u +%Y%m%dT%H%M%SZ)-$$}"
export MAX_WORKERS="${MAX_WORKERS:-32}"

exec "$SCRIPT_DIR/run.sh"
