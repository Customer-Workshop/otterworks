#!/bin/bash
# ETL runner — sets up environment and runs the specified script
# Usage: ./run.sh <script_name.py>
source /opt/etl/.env 2>/dev/null || true
export PYTHONPATH=/opt/etl
cd /opt/etl/scripts
python3 "$1"
