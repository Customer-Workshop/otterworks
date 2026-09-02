#!/usr/bin/env python3
"""Validate the committed Jobs API snapshot for the CUSTBILL workflow."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

EXPECTED_DAG = {"ingest": [], "parse": ["ingest"], "finance": ["parse"]}


def task_graph(settings: dict) -> dict[str, list[str]]:
    """Return the task dependency graph from a Jobs API settings object."""
    return {
        task.get("task_key", "<missing>"): sorted(
            dependency.get("task_key", "<missing>")
            for dependency in task.get("depends_on", [])
        )
        for task in settings.get("tasks", [])
    }


def _pause_status(settings: dict) -> Any:
    schedule = settings.get("schedule") or {}
    trigger = settings.get("trigger") or {}
    return schedule.get("pause_status") or trigger.get("pause_status")


def _parameter_names(settings: dict) -> set[str]:
    parameters = settings.get("parameters") or []
    if isinstance(parameters, dict):
        return set(parameters)
    return {
        parameter.get("name")
        for parameter in parameters
        if isinstance(parameter, dict) and parameter.get("name")
    }


def assert_job(settings: dict, require_retries: bool = True) -> list[str]:
    """Return short descriptions of workflow settings that violate U9."""
    failures: list[str] = []
    graph = task_graph(settings)
    if graph != EXPECTED_DAG:
        failures.append(f"task_graph={graph!r} (expected {EXPECTED_DAG!r})")

    concurrency = settings.get("max_concurrent_runs")
    if concurrency != 1:
        failures.append(f"max_concurrent_runs={concurrency!r} (expected 1)")

    pause_status = _pause_status(settings)
    if pause_status != "PAUSED":
        failures.append(f"pause_status={pause_status!r} (expected 'PAUSED')")

    for task in settings.get("tasks", []):
        task_key = task.get("task_key", "<missing>")
        if task.get("existing_cluster_id") or task.get("new_cluster"):
            failures.append(f"task {task_key} has cluster configuration (serverless expected)")
        if require_retries:
            max_retries = task.get("max_retries")
            if max_retries != 2:
                failures.append(f"task {task_key} max_retries={max_retries!r} (expected 2)")
            interval = task.get("min_retry_interval_millis")
            if interval != 300000:
                failures.append(
                    f"task {task_key} min_retry_interval_millis={interval!r} (expected 300000)"
                )
            retry_on_timeout = task.get("retry_on_timeout")
            if retry_on_timeout is not False:
                failures.append(
                    f"task {task_key} retry_on_timeout={retry_on_timeout!r} (expected False)"
                )

    recipients = (settings.get("email_notifications") or {}).get("on_failure", [])
    if not recipients:
        failures.append("on_failure recipients are empty (expected at least one)")

    names = _parameter_names(settings)
    for name in ("ns", "report_date"):
        if name not in names:
            failures.append(f"missing job parameter {name!r}")
    return failures


def load_snapshot(path: Path) -> dict:
    """Load either a full Jobs API get response or a bare settings object."""
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("snapshot must contain a JSON object")
    settings = payload.get("settings")
    return settings if isinstance(settings, dict) else payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-retries", action="store_true", help="skip retry-setting checks")
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args(argv)
    failures = assert_job(load_snapshot(args.snapshot), require_retries=not args.no_retries)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("PASS: CUSTBILL workflow job settings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
