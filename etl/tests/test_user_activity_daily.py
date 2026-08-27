import gzip
import json
from datetime import datetime, timedelta, timezone

import boto3


def _put_activity(s3, ds, rows):
    date = datetime.strptime(ds, "%Y-%m-%d")
    key = (
        f"analytics/daily/year={date:%Y}/month={date:%m}/day={date:%d}/"
        "top_users.jsonl.gz"
    )
    body = gzip.compress(("\n".join(json.dumps(row) for row in rows) + "\n").encode())
    s3.put_object(Bucket="otterworks-data-lake", Key=key, Body=body)


def test_user_activity_aggregates_days_and_writes_pointer(
    moto_aws, etl_config, load_script, postgres_service
):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="otterworks-data-lake")
    today = datetime.now(timezone.utc).date()
    _put_activity(
        s3,
        str(today),
        [
            {"user_id": "alice", "total": 3, "actions": {"edit": 2, "comment": 1}},
            {"user_id": "bob", "total": 1, "actions": {"upload": 1}},
        ],
    )
    _put_activity(
        s3,
        str(today - timedelta(days=2)),
        [
            {"user_id": "alice", "total": 4, "actions": {"edit": 4}},
            {"user_id": "carol", "total": 2, "actions": {"share": 2}},
        ],
    )
    import psycopg2

    conn = psycopg2.connect(
        host=postgres_service["host"],
        port=postgres_service["port"],
        dbname="etl",
        user="etl",
        password="postgres",
    )
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO analytics_daily_summary (
                    report_date, active_users, active_documents, active_files,
                    total_events, documents_created, documents_edited,
                    comments_added, files_uploaded, files_shared,
                    files_deleted, bytes_uploaded, updated_at
                ) VALUES (%s, 2, 3, 4, 10, 2, 3, 1, 2, 1, 0, 100, NOW()),
                           (%s, 4, 5, 6, 20, 3, 4, 2, 3, 2, 1, 200, NOW())
                """,
                (today, today - timedelta(days=2)),
            )
    conn.close()
    etl_config(database_port=postgres_service["port"])

    load_script("user_activity_daily.py").main()

    ds = str(today)
    report = json.loads(
        s3.get_object(
            Bucket="otterworks-data-lake",
            Key=f"reports/user-activity/{ds}/activity_report.json",
        )["Body"].read()
    )
    assert report["trends"]["total_events"] == 30
    assert report["trends"]["peak_active_users"] == 4
    assert report["trends"]["reporting_days"] == 2
    summaries = {row["user_id"]: row for row in report["user_summaries"]}
    assert summaries["alice"]["total_actions"] == 7
    assert summaries["alice"]["active_days"] == 2
    assert summaries["alice"]["actions_by_type"] == {"edit": 6, "comment": 1}
    assert summaries["bob"]["active_days"] == 1
    latest = json.loads(
        s3.get_object(
            Bucket="otterworks-data-lake",
            Key="reports/user-activity/latest/activity_report.json",
        )["Body"].read()
    )
    assert latest["report_date"] == ds
    lines = s3.get_object(
        Bucket="otterworks-data-lake",
        Key=f"reports/user-activity/{ds}/user_summaries.jsonl",
    )["Body"].read().decode().strip().splitlines()
    assert len(lines) == 3
