"""Shared helpers for the OtterWorks Airflow DAGs.

This package lives inside the DAGs folder so that it is importable as
``common.*`` from any DAG file without extra ``sys.path`` manipulation
(Airflow puts the DAGs folder on ``sys.path``).
"""
