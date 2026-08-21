#!/usr/bin/env bash
# Local verification loop for the OtterWorks Airflow DAGs.
#
#   ./check.sh setup    create .venv and install the pinned requirements
#   ./check.sh import   DAG-import check (fails on any DAG import error)
#   ./check.sh test     pytest suite
#   ./check.sh          import + test
#
set -euo pipefail

cd "$(dirname "$0")"
AIRFLOW_DIR="$PWD"
VENV="$AIRFLOW_DIR/.venv"
# Prefer the local venv; fall back to the ambient interpreter (CI installs the
# pinned requirements directly).
if [ -x "$VENV/bin/python" ]; then
  PY="$VENV/bin/python"
else
  PY="$(command -v python3 || command -v python)"
fi

export AIRFLOW_HOME="$AIRFLOW_DIR/.airflow-test-home"
export AIRFLOW__CORE__DAGS_FOLDER="$AIRFLOW_DIR/dags"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export AIRFLOW__CORE__UNIT_TEST_MODE=True
export AWS_DEFAULT_REGION=us-east-1

setup() {
  local python_bin="${PYTHON_BIN:-python3.11}"
  command -v "$python_bin" >/dev/null || python_bin="$(ls -d "$HOME"/.pyenv/versions/3.11.*/bin/python 2>/dev/null | head -1)"
  [ -n "$python_bin" ] || { echo "Python 3.11 is required (Airflow 2.8 does not support 3.12)"; exit 1; }
  "$python_bin" -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip
  "$VENV/bin/pip" install -r requirements-dev.txt -c constraints-2.8.4-python3.11.txt
}

import_check() {
  echo "== DAG import check =="
  "$PY" - <<'PY'
import sys
from pathlib import Path

dags = Path.cwd() / "dags"
sys.path.insert(0, str(dags))
from airflow.models import DagBag  # noqa: E402

bag = DagBag(dag_folder=str(dags), include_examples=False)
if bag.import_errors:
    for path, err in bag.import_errors.items():
        print(f"IMPORT ERROR {path}\n{err}", file=sys.stderr)
    sys.exit(1)
# `bag.dags[...]` (not `get_dag`) keeps the check free of any metadata DB.
for dag_id, dag in sorted(bag.dags.items()):
    print(f"OK  {dag_id:38s} schedule={dag.schedule_interval!s:12s} tasks={len(dag.tasks)}")
print(f"{len(bag.dag_ids)} DAG(s) imported with no errors")
PY
}

run_tests() {
  echo "== pytest =="
  "$PY" -m pytest "$@"
}

if [ "${1:-all}" != "setup" ]; then
  "$PY" -c "import airflow" 2>/dev/null || {
    echo "Airflow is not importable — run ./check.sh setup first" >&2
    exit 1
  }
fi

case "${1:-all}" in
  setup) setup ;;
  import) import_check ;;
  test) shift; run_tests "$@" ;;
  all) import_check; run_tests ;;
  *) echo "usage: $0 [setup|import|test|all]"; exit 2 ;;
esac
