"""Minimal Databricks REST client for the bronze_core migration unit.

Only the calls this unit needs: SQL against the pre-existing serverless warehouse, uploads
to the pre-existing landing volume, workspace imports under the parent-owned notebook root,
and serverless one-off notebook runs. It never creates a cluster, a warehouse, or any other
hourly-cost resource, and it fails loudly instead of working around a denied call.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterable, Sequence
from typing import Any

import requests

WAREHOUSE_ID = "565cd2fd713738c4"  # pre-existing "Serverless Starter Warehouse"


class DbxError(RuntimeError):
    """A Databricks API call failed; the message carries the exact request and response."""


class Dbx:
    def __init__(self, host: str | None = None, token: str | None = None, timeout: int = 300):
        host = host or os.environ.get("DATABRICKS_HOST") or os.environ.get("DATABRICKS_DEMO_HOST")
        token = (
            token
            or os.environ.get("DATABRICKS_TOKEN")
            or os.environ.get("DATABRICKS_DEMO_TOKEN")
        )
        if not host or not token:
            raise DbxError(
                "set DATABRICKS_HOST/DATABRICKS_TOKEN (or DATABRICKS_DEMO_HOST/"
                "DATABRICKS_DEMO_TOKEN); no credential is ever read from the branch"
            )
        self.host = host.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {token}"})
        self.timeout = timeout

    # -- plumbing ---------------------------------------------------------------
    def _call(self, method: str, path: str, **kw: Any) -> Any:
        url = f"{self.host}{path}"
        resp = self._session.request(method, url, timeout=self.timeout, **kw)
        if resp.status_code >= 400:
            raise DbxError(f"{method} {path} -> {resp.status_code} {resp.text[:2000]}")
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.content

    # -- SQL ------------------------------------------------------------------
    def sql(self, statement: str, warehouse_id: str = WAREHOUSE_ID) -> list[list[Any]]:
        body = {
            "statement": statement,
            "warehouse_id": warehouse_id,
            "wait_timeout": "50s",
            "on_wait_timeout": "CONTINUE",
            "disposition": "INLINE",
            "format": "JSON_ARRAY",
        }
        res = self._call("POST", "/api/2.0/sql/statements", json=body)
        sid = res["statement_id"]
        while res["status"]["state"] in ("PENDING", "RUNNING"):
            time.sleep(2)
            res = self._call("GET", f"/api/2.0/sql/statements/{sid}")
        state = res["status"]["state"]
        if state != "SUCCEEDED":
            raise DbxError(
                f"SQL {state}: {json.dumps(res['status'])[:1500]}\nstatement: {statement[:800]}"
            )
        rows: list[list[Any]] = []
        result = res.get("result") or {}
        rows.extend(result.get("data_array") or [])
        link = result.get("next_chunk_internal_link")
        while link:
            chunk = self._call("GET", link)
            rows.extend(chunk.get("data_array") or [])
            link = chunk.get("next_chunk_internal_link")
        return rows

    def scalar(self, statement: str) -> Any:
        rows = self.sql(statement)
        return rows[0][0] if rows else None

    # -- files / workspace ----------------------------------------------------
    def upload(self, volume_path: str, local_path: str) -> None:
        with open(local_path, "rb") as fh:
            self._call(
                "PUT",
                f"/api/2.0/fs/files{volume_path}",
                params={"overwrite": "true"},
                data=fh.read(),
                headers={"Content-Type": "application/octet-stream"},
            )

    def mkdirs_workspace(self, path: str) -> None:
        self._call("POST", "/api/2.0/workspace/mkdirs", json={"path": path})

    def import_workspace(self, path: str, local_path: str, fmt: str, language: str | None = None) -> None:
        import base64

        with open(local_path, "rb") as fh:
            content = base64.b64encode(fh.read()).decode()
        body = {"path": path, "content": content, "format": fmt, "overwrite": True}
        if language:
            body["language"] = language
        self._call("POST", "/api/2.0/workspace/import", json=body)

    # -- serverless job runs --------------------------------------------------
    def submit_notebook_run(
        self, run_name: str, notebook_path: str, params: dict[str, str]
    ) -> int:
        body = {
            "run_name": run_name,
            "tasks": [
                {
                    "task_key": "load",
                    "notebook_task": {
                        "notebook_path": notebook_path,
                        "base_parameters": params,
                    },
                }
            ],
        }
        return int(self._call("POST", "/api/2.2/jobs/runs/submit", json=body)["run_id"])

    def wait_run(self, run_id: int, poll: int = 15, limit: int = 7200) -> dict[str, Any]:
        deadline = time.time() + limit
        while True:
            run = self._call("GET", "/api/2.2/jobs/runs/get", params={"run_id": run_id})
            state = run["status"]["state"] if "status" in run else run["state"]["life_cycle_state"]
            if state in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR", "SUCCESS", "FAILED"):
                return run
            if time.time() > deadline:
                raise DbxError(f"run {run_id} still {state} after {limit}s")
            time.sleep(poll)

    def run_output(self, run_id: int) -> dict[str, Any]:
        run = self._call("GET", "/api/2.2/jobs/runs/get", params={"run_id": run_id})
        task_run_id = run["tasks"][0]["run_id"]
        return self._call(
            "GET", "/api/2.1/jobs/runs/get-output", params={"run_id": task_run_id}
        )

    def read_volume_file(self, volume_path: str) -> bytes:
        url = f"{self.host}/api/2.0/fs/files{volume_path}"
        resp = self._session.get(url, timeout=self.timeout)
        if resp.status_code >= 400:
            raise DbxError(f"GET files{volume_path} -> {resp.status_code} {resp.text[:2000]}")
        return resp.content


def sql_str(value: str) -> str:
    """Single-quoted SQL literal."""
    return "'" + value.replace("'", "''") + "'"


def sql_in(values: Iterable[str]) -> str:
    return ", ".join(sql_str(v) for v in values)


def rows_to_dicts(rows: Sequence[Sequence[Any]], columns: Sequence[str]) -> list[dict[str, Any]]:
    return [dict(zip(columns, r)) for r in rows]
