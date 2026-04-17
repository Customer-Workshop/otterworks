"""Shared pytest configuration and fixtures for ETL tests."""

import sys
from pathlib import Path

# Add dags directory to Python path so tests can import DAG modules
dags_dir = Path(__file__).parent.parent / "dags"
sys.path.insert(0, str(dags_dir))
