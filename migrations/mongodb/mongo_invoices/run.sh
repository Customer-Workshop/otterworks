#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: $0 migrate|recon|selftest [args...]" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../../.." && pwd)"

case "$1" in
  migrate|recon|selftest)
    action="$1"
    shift
    ;;
  *)
    echo "usage: $0 migrate|recon|selftest [args...]" >&2
    exit 2
    ;;
esac

exec "$repo_root/scripts/tp-run-deterministic.sh" \
  env PYTHONPATH="$script_dir${PYTHONPATH:+:$PYTHONPATH}" \
  uv run --no-project \
  --with oracledb==2.5.1 \
  --with pymongo==4.10.1 \
  "$script_dir/$action.py" "$@"
