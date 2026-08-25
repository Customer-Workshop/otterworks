#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: $0 migrate|recon|selftest [args...]" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../../.." && pwd)"
venv_python="$repo_root/.venv-tp-mongo/bin/python"

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

if [ ! -x "$venv_python" ]; then
  echo "missing virtualenv interpreter: $venv_python" >&2
  exit 1
fi

exec "$repo_root/scripts/tp-run-deterministic.sh" \
  env PYTHONPATH="$script_dir${PYTHONPATH:+:$PYTHONPATH}" \
  "$venv_python" "$script_dir/$action.py" "$@"
