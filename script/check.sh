#!/usr/bin/env bash
# Run all repository checks from the project root.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON="${PYTHON:-venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
    echo "Python 环境不可用: $PYTHON" >&2
    exit 2
fi

find . -path './venv' -prune -o -path './studio/node_modules' -prune -o -path './runs' -prune -o -name '*.py' -exec "$PYTHON" -m py_compile {} +
"$PYTHON" -m unittest discover -s tests -v
"$PYTHON" -m unittest discover -s studio/tests -v

for shell_file in script/*.sh; do
    bash -n "$shell_file"
done

(cd studio && npm run test:sites && npm run build)
