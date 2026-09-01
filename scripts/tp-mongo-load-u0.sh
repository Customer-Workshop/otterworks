#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
exec uv run --no-project --with 'pymongo[srv]==4.10.1' --with oracledb==2.5.1 "$REPO_ROOT/scripts/tp_mongo/load_u0.py" "$@"
