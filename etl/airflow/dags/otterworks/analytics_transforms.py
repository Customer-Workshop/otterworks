"""Pure transformation logic for the daily analytics pipeline.

Re-implements the pandas aggregation in ``etl/scripts/analytics_daily.py`` as
plain-Python, event-at-a-time functions that produce identical output (same
summary / hourly / top-user structures, same S3 keys, same SQL) without
loading a DataFrame. No AWS or Airflow imports so it is unit testable.
"""

from __future__ import annotations

import gzip
import io
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

Event = dict[str, Any]

USER_ID_FIELDS = ("ownerId", "editedBy", "authorId", "deletedBy", "userId")
UNKNOWN = "unknown"
TOP_USERS_LIMIT = 100
HIGHLIGHT_USERS_LIMIT = 5

ANALYTICS_UPSERT_SQL = """
    INSERT INTO analytics_daily_summary (
        report_date, active_users, active_documents, active_files,
        total_events, documents_created, documents_edited,
        comments_added, files_uploaded, files_shared,
        files_deleted, bytes_uploaded, updated_at
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
    )
    ON CONFLICT (report_date) DO UPDATE SET
        active_users = EXCLUDED.active_users,
        active_documents = EXCLUDED.active_documents,
        active_files = EXCLUDED.active_files,
        total_events = EXCLUDED.total_events,
        documents_created = EXCLUDED.documents_created,
        documents_edited = EXCLUDED.documents_edited,
        comments_added = EXCLUDED.comments_added,
        files_uploaded = EXCLUDED.files_uploaded,
        files_shared = EXCLUDED.files_shared,
        files_deleted = EXCLUDED.files_deleted,
        bytes_uploaded = EXCLUDED.bytes_uploaded,
        updated_at = NOW();
"""

SUMMARY_COLUMNS = (
    "active_users",
    "active_documents",
    "active_files",
    "total_events",
    "documents_created",
    "documents_edited",
    "comments_added",
    "files_uploaded",
    "files_shared",
    "files_deleted",
    "bytes_uploaded",
)


# ---- S3 key layout -------------------------------------------------------


def partition_key(analytics_prefix: str, report_date: str) -> str:
    year, month, day = report_date[:4], report_date[5:7], report_date[8:10]
    return f"{analytics_prefix}/year={year}/month={month}/day={day}"


def summary_key(analytics_prefix: str, report_date: str) -> str:
    return f"{partition_key(analytics_prefix, report_date)}/summary.json.gz"


def hourly_breakdown_key(analytics_prefix: str, report_date: str) -> str:
    return f"{partition_key(analytics_prefix, report_date)}/hourly_breakdown.json.gz"


def top_users_key(analytics_prefix: str, report_date: str) -> str:
    return f"{partition_key(analytics_prefix, report_date)}/top_users.jsonl.gz"


def analytics_report_key(report_date: str) -> str:
    return f"reports/analytics/daily/{report_date}/report.json"


# ---- Serialisation ---------------------------------------------------------


def encode_gzip_json(payload: Any) -> bytes:
    return gzip.compress(json.dumps(payload, indent=2).encode("utf-8"))


def encode_gzip_jsonl(rows: list[Any]) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        for row in rows:
            gz.write(json.dumps(row).encode("utf-8"))
            gz.write(b"\n")
    return buf.getvalue()


def encode_json(payload: Any) -> bytes:
    return json.dumps(payload, indent=2).encode("utf-8")


# ---- Event normalisation ---------------------------------------------------


def normalize_dynamodb_item(item: dict[str, Any]) -> Event:
    """Convert boto3 ``Decimal`` values to ``int``/``float`` for JSON output."""
    out: Event = {}
    for key, value in item.items():
        if isinstance(value, Decimal):
            out[key] = int(value) if value == int(value) else float(value)
        else:
            out[key] = value
    return out


def _not_null(value: Any) -> bool:
    """``pandas.notna`` equivalent: rejects ``None`` and float NaN only."""
    if value is None:
        return False
    return not (isinstance(value, float) and value != value)


def _is_present(value: Any) -> bool:
    """Non-null and not the empty string (legacy user-id resolution rule)."""
    return _not_null(value) and value != ""


def resolve_event_type(event: Event) -> str:
    if _is_present(event.get("eventType")):
        return event["eventType"]
    if _is_present(event.get("event_type")):
        return event["event_type"]
    return UNKNOWN


def resolve_user_id(event: Event) -> str:
    for field in USER_ID_FIELDS:
        value = event.get(field)
        if _is_present(value):
            return value
    return UNKNOWN


def parse_hour(timestamp: Any) -> str:
    """Two-digit hour of an ISO-8601 string in its own offset, else ``"00"``."""
    if isinstance(timestamp, str):
        try:
            return "%02d" % datetime.fromisoformat(timestamp.replace("Z", "+00:00")).hour
        except ValueError:
            return "00"
    return "00"


def _as_number(value: Any) -> int | float:
    return value if _not_null(value) else 0


# ---- Aggregation -----------------------------------------------------------


def aggregate_events(events: list[Event]) -> dict[str, Any]:
    """Aggregate raw events into the legacy analytics structures.

    Returns a dict with ``summary``, ``hourly_breakdown``, ``user_summaries``,
    ``document_metrics`` and ``file_metrics`` exactly as the legacy script
    computed them (top 100 users by total actions, hours sorted ascending).
    """
    user_action_counts: dict[str, dict[str, int]] = {}
    hourly_breakdown: dict[str, dict[str, int]] = {}
    active_users: set[str] = set()
    active_documents: set[Any] = set()
    active_files: set[Any] = set()

    documents_created = documents_edited = comments_added = 0
    files_uploaded = files_shared = files_deleted = 0
    bytes_uploaded: int | float = 0

    for event in events:
        etype = resolve_event_type(event)
        uid = resolve_user_id(event)
        hour = parse_hour(event.get("timestamp"))

        if uid != UNKNOWN:
            active_users.add(uid)
        user_action_counts.setdefault(uid, {})
        user_action_counts[uid][etype] = user_action_counts[uid].get(etype, 0) + 1

        hourly_breakdown.setdefault(hour, {})
        hourly_breakdown[hour][etype] = hourly_breakdown[hour].get(etype, 0) + 1

        document_id = event.get("documentId")
        file_id = event.get("fileId")

        if etype == "document_created":
            documents_created += 1
            if _not_null(document_id):
                active_documents.add(document_id)
        elif etype == "document_edited":
            documents_edited += 1
            if _not_null(document_id):
                active_documents.add(document_id)
        elif etype == "comment_added":
            comments_added += 1
        elif etype == "file_uploaded":
            files_uploaded += 1
            bytes_uploaded += _as_number(event.get("sizeBytes"))
            if _not_null(file_id):
                active_files.add(file_id)
        elif etype == "file_shared":
            files_shared += 1
            if _not_null(file_id):
                active_files.add(file_id)
        elif etype == "file_deleted":
            files_deleted += 1
            if _not_null(file_id):
                active_files.add(file_id)

    bytes_uploaded = int(bytes_uploaded)

    user_summaries = [
        {"user_id": uid, "actions": actions, "total": sum(actions.values())}
        for uid, actions in user_action_counts.items()
    ]
    user_summaries.sort(key=lambda x: x["total"], reverse=True)
    user_summaries = user_summaries[:TOP_USERS_LIMIT]

    summary = {
        "active_users": len(active_users),
        "active_documents": len(active_documents),
        "active_files": len(active_files),
        "total_events": len(events),
        "documents_created": documents_created,
        "documents_edited": documents_edited,
        "comments_added": comments_added,
        "files_uploaded": files_uploaded,
        "files_shared": files_shared,
        "files_deleted": files_deleted,
        "bytes_uploaded": bytes_uploaded,
    }

    return {
        "summary": summary,
        "hourly_breakdown": dict(sorted(hourly_breakdown.items())),
        "user_summaries": user_summaries,
        "document_metrics": {
            "created": documents_created,
            "edited": documents_edited,
            "comments": comments_added,
        },
        "file_metrics": {
            "uploaded": files_uploaded,
            "shared": files_shared,
            "deleted": files_deleted,
            "bytes_uploaded": bytes_uploaded,
        },
    }


def summary_upsert_params(report_date: str, summary: dict[str, Any]) -> tuple[Any, ...]:
    """Positional parameters for :data:`ANALYTICS_UPSERT_SQL`."""
    return (report_date, *(summary[column] for column in SUMMARY_COLUMNS))


def find_peak_hour(hourly_breakdown: dict[str, dict[str, int]]) -> dict[str, Any] | None:
    if not hourly_breakdown:
        return None
    hour, counts = max(hourly_breakdown.items(), key=lambda x: sum(x[1].values()))
    return {"hour": hour, "event_count": sum(counts.values())}


def build_analytics_report(
    *,
    report_date: str,
    generated_at: str,
    aggregates: dict[str, Any],
) -> dict[str, Any]:
    return {
        "report_type": "daily_analytics",
        "report_date": report_date,
        "generated_at": generated_at,
        "summary": aggregates["summary"],
        "highlights": {
            "peak_hour": find_peak_hour(aggregates["hourly_breakdown"]),
            "most_active_users": [
                u["user_id"] for u in aggregates["user_summaries"][:HIGHLIGHT_USERS_LIMIT]
            ],
        },
        "document_metrics": aggregates["document_metrics"],
        "file_metrics": aggregates["file_metrics"],
    }
