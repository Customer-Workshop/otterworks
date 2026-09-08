"""Shared building blocks for the OtterWorks Airflow DAGs.

Pure transformation logic lives in ``*_transforms`` modules so it can be unit
tested without Airflow or AWS; ``common`` holds DAG defaults, Connection /
Variable names and the structured logger factory.
"""
