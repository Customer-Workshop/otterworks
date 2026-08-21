"""Thin wrappers over the Airflow provider hooks.

The legacy scripts built raw ``boto3`` clients and ``psycopg2`` connections
inline with credentials read from ``config.ini``. Everything here goes through
a provider hook bound to a named Connection instead, so credentials live in
Airflow (or its secrets backend) and connections are reused.
"""

from __future__ import annotations

import gzip
import json
from typing import Any, Callable, Iterator

from airflow.providers.amazon.aws.hooks.dynamodb import DynamoDBHook
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.amazon.aws.hooks.sqs import SqsHook
from airflow.providers.postgres.hooks.postgres import PostgresHook

from .config import AWS_CONN_ID, POSTGRES_CONN_ID
from .logging_utils import get_logger

log = get_logger(__name__)


def get_s3_hook() -> S3Hook:
    return S3Hook(aws_conn_id=AWS_CONN_ID)


def get_sqs_hook() -> SqsHook:
    return SqsHook(aws_conn_id=AWS_CONN_ID)


def get_dynamodb_hook(table_name: str) -> DynamoDBHook:
    return DynamoDBHook(aws_conn_id=AWS_CONN_ID, table_name=table_name)


def get_dynamodb_table(table_name: str) -> Any:
    """Return a boto3 DynamoDB ``Table`` resource bound to ``aws_default``."""
    return get_dynamodb_hook(table_name).get_conn().Table(table_name)


def get_postgres_hook() -> PostgresHook:
    return PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)


def scan_dynamodb_table(table: Any, **scan_kwargs: Any) -> Iterator[dict[str, Any]]:
    """Yield every item of a paginated ``Table.scan``.

    Unlike the legacy inline loops this never swallows an error: a failed page
    propagates so the task fails and Airflow retries it.
    """
    kwargs = dict(scan_kwargs)
    while True:
        response = table.scan(**kwargs)
        yield from response.get("Items", [])
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            return
        kwargs["ExclusiveStartKey"] = last_key


def put_json_object(
    bucket: str,
    key: str,
    payload: Any,
    *,
    compress: bool = False,
    indent: int | None = 2,
) -> str:
    """Write a JSON document to S3, overwriting any previous copy.

    Overwriting (rather than appending or suffixing with a timestamp) is what
    makes the loaders idempotent: re-running a task for the same logical date
    reproduces the same object at the same key.
    """
    body = json.dumps(payload, indent=indent, default=str).encode("utf-8")
    if compress:
        body = gzip.compress(body, mtime=0)
    get_s3_hook().load_bytes(body, key=key, bucket_name=bucket, replace=True)
    log.info("Wrote s3://%s/%s (%d bytes)", bucket, key, len(body))
    return key


def put_jsonl_object(
    bucket: str,
    key: str,
    rows: list[Any],
    *,
    compress: bool = True,
) -> str:
    """Write an iterable of records as (optionally gzipped) JSON Lines."""
    text = "".join(json.dumps(row, default=str) + "\n" for row in rows)
    body = text.encode("utf-8")
    if compress:
        body = gzip.compress(body, mtime=0)
    get_s3_hook().load_bytes(body, key=key, bucket_name=bucket, replace=True)
    log.info("Wrote s3://%s/%s (%d rows)", bucket, key, len(rows))
    return key


def run_with_failure_summary(
    items: list[Any],
    action: Callable[[Any], None],
    *,
    description: str,
) -> dict[str, Any]:
    """Apply ``action`` to every item and fail the task if any item failed.

    The legacy scripts counted failures and exited 0 regardless. Here the
    per-item error is logged with its context, every item is still attempted,
    and the task then raises so Airflow retries and alerts.
    """
    failures: list[dict[str, str]] = []
    succeeded = 0
    for item in items:
        try:
            action(item)
            succeeded += 1
        except Exception as exc:  # noqa: BLE001 - re-raised in aggregate below
            log.error("%s failed for %r: %s", description, item, exc)
            failures.append({"item": repr(item), "error": str(exc)})
    if failures:
        raise RuntimeError(
            f"{description}: {len(failures)} of {len(items)} items failed; "
            f"first error: {failures[0]['error']}"
        )
    return {"succeeded": succeeded, "failed": 0}
