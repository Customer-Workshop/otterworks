"""Verbatim extraction of the legacy pandas aggregation from
``etl/scripts/analytics_daily.py`` (lines "Transform and aggregate using
pandas" through "Build aggregated result", plus the peak-hour highlight).

Used only as a parity oracle in tests: the Airflow transforms must produce
byte-for-byte identical JSON to this code for the same event stream.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd


def legacy_aggregate(all_events):  # noqa: C901 - copied as-is from the legacy script
    df = pd.DataFrame(all_events)

    # Normalize event type field name
    if "event_type" in df.columns and "eventType" not in df.columns:
        df["eventType"] = df["event_type"]
    if "eventType" not in df.columns:
        df["eventType"] = "unknown"

    # Resolve user ID from whichever field is populated
    df["resolved_user_id"] = "unknown"
    for col in ["ownerId", "editedBy", "authorId", "deletedBy", "userId"]:
        if col in df.columns:
            mask = (df["resolved_user_id"] == "unknown") & df[col].notna() & (df[col] != "")
            df.loc[mask, "resolved_user_id"] = df.loc[mask, col]

    # Parse timestamps for hourly bucketing
    df["hour"] = "00"
    if "timestamp" in df.columns:

        def parse_hour(ts):
            try:
                if isinstance(ts, str):
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    return "%02d" % dt.hour  # noqa: UP031 - verbatim legacy code
            except Exception:
                pass
            return "00"

        df["hour"] = df["timestamp"].apply(parse_hour)

    # ---- Aggregate user actions ----
    active_users = set(df["resolved_user_id"].unique()) - {"unknown"}
    user_action_counts = {}
    for _, row in df.iterrows():
        uid = row["resolved_user_id"]
        etype = row.get("eventType", "unknown")
        if uid not in user_action_counts:
            user_action_counts[uid] = {}
        if etype not in user_action_counts[uid]:
            user_action_counts[uid][etype] = 0
        user_action_counts[uid][etype] += 1

    # Build top users list (top 100 by total actions)
    user_summaries = []
    for uid, actions in user_action_counts.items():
        total = sum(actions.values())
        user_summaries.append({"user_id": uid, "actions": actions, "total": total})
    user_summaries.sort(key=lambda x: x["total"], reverse=True)
    user_summaries = user_summaries[:100]

    # ---- Document metrics ----
    documents_created = 0
    documents_edited = 0
    comments_added = 0
    active_documents = set()

    if "eventType" in df.columns:
        doc_created = df[df["eventType"] == "document_created"]
        documents_created = len(doc_created)
        if "documentId" in df.columns:
            active_documents.update(doc_created["documentId"].dropna().unique())

        doc_edited = df[df["eventType"] == "document_edited"]
        documents_edited = len(doc_edited)
        if "documentId" in df.columns:
            active_documents.update(doc_edited["documentId"].dropna().unique())

        doc_comments = df[df["eventType"] == "comment_added"]
        comments_added = len(doc_comments)

    # ---- File metrics ----
    files_uploaded = 0
    files_shared = 0
    files_deleted = 0
    bytes_uploaded = 0
    active_files = set()

    if "eventType" in df.columns:
        uploaded = df[df["eventType"] == "file_uploaded"]
        files_uploaded = len(uploaded)
        if "sizeBytes" in df.columns:
            bytes_uploaded = int(uploaded["sizeBytes"].fillna(0).sum())
        if "fileId" in df.columns:
            active_files.update(uploaded["fileId"].dropna().unique())

        shared = df[df["eventType"] == "file_shared"]
        files_shared = len(shared)
        if "fileId" in df.columns:
            active_files.update(shared["fileId"].dropna().unique())

        deleted = df[df["eventType"] == "file_deleted"]
        files_deleted = len(deleted)
        if "fileId" in df.columns:
            active_files.update(deleted["fileId"].dropna().unique())

    # ---- Hourly breakdown ----
    hourly_breakdown = {}
    for _, row in df.iterrows():
        h = row.get("hour", "00")
        etype = row.get("eventType", "unknown")
        if h not in hourly_breakdown:
            hourly_breakdown[h] = {}
        if etype not in hourly_breakdown[h]:
            hourly_breakdown[h][etype] = 0
        hourly_breakdown[h][etype] += 1

    # Sort hourly breakdown
    hourly_breakdown = dict(sorted(hourly_breakdown.items()))

    # ---- Build aggregated result ----
    document_metrics = {
        "created": documents_created,
        "edited": documents_edited,
        "comments": comments_added,
    }
    file_metrics = {
        "uploaded": files_uploaded,
        "shared": files_shared,
        "deleted": files_deleted,
        "bytes_uploaded": bytes_uploaded,
    }

    summary = {
        "active_users": len(active_users),
        "active_documents": len(active_documents),
        "active_files": len(active_files),
        "total_events": len(all_events),
        "documents_created": documents_created,
        "documents_edited": documents_edited,
        "comments_added": comments_added,
        "files_uploaded": files_uploaded,
        "files_shared": files_shared,
        "files_deleted": files_deleted,
        "bytes_uploaded": bytes_uploaded,
    }

    peak_hour = None
    if hourly_breakdown:
        peak = max(hourly_breakdown.items(), key=lambda x: sum(x[1].values()))
        peak_hour = {"hour": peak[0], "event_count": sum(peak[1].values())}

    return {
        "summary": summary,
        "hourly_breakdown": hourly_breakdown,
        "user_summaries": user_summaries,
        "document_metrics": document_metrics,
        "file_metrics": file_metrics,
        "peak_hour": peak_hour,
        "most_active_users": [u["user_id"] for u in user_summaries[:5]],
    }
