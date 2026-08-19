#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec uv run --no-project --with 'pymongo[srv]==4.10.1' "$REPO_ROOT/scripts/tp_break/mongodb.py" "$@"
