#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export USER_COUNT=100
export RUN_DIR="${RUN_DIR:-logs_100_qwen3_30b_10td}"
export MAX_WORKERS="${MAX_WORKERS:-32}"

exec "$SCRIPT_DIR/run.sh"
