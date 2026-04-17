"""
OtterWorks User Activity Report Pipeline

Daily pipeline that queries analytics aggregates, generates per-user
activity summaries, and stores them in S3 for admin-service to serve.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook

logger = logging.getLogger(__name__)

# Configuration
_DEFAULT_S3_BUCKET = "otterworks-data-lake"
S3_REPORTS_PREFIX = "reports/user-activity"


def _get_s3_bucket():
    from airflow.models import Variable
    return Variable.get("otterworks_data_lake_bucket", default_var=_DEFAULT_S3_BUCKET)


POSTGRES_CONN_ID = "otterworks_postgres"
AWS_CONN_ID = "aws_default"
LOOKBACK_DAYS = 30

default_args = {
    "owner": "otterworks-data",
    "depends_on_past": False,
    "email_on_failure": True,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def query_analytics_aggregates(**context):
    """Query PostgreSQL for analytics aggregates over the lookback window.

    Retrieves daily summary data for the past LOOKBACK_DAYS to build
    trend information for the activity report.
    """
    ds = context["ds"]
    pg_hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)

    summary_sql = """
        SELECT
            report_date,
            active_users,
            active_documents,
            active_files,
            total_events,
            documents_created,
            documents_edited,
            comments_added,
            files_uploaded,
            files_shared,
            files_deleted,
            bytes_uploaded
        FROM analytics_daily_summary
        WHERE report_date BETWEEN %s::date - interval '%s days' AND %s::date
        ORDER BY report_date;
    """

    rows = pg_hook.get_records(summary_sql, parameters=(ds, LOOKBACK_DAYS, ds))
    columns = [
        "report_date",
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
    ]

    records = []
    for row in rows:
        record = {}
        for i, col in enumerate(columns):
            val = row[i]
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            record[col] = val
        records.append(record)

    logger.info("Retrieved %d daily summary records for lookback window", len(records))
    return records


def query_per_user_activity(**context):
    """Query per-user activity data from the analytics data lake.

    Reads per-user activity data from S3 (top_users JSONL files)
    for the past LOOKBACK_DAYS and aggregates per-user totals.
    """
    ds = context["ds"]
    s3_hook = S3Hook(aws_conn_id=AWS_CONN_ID)
    user_totals = {}

    execution_date = datetime.strptime(ds, "%Y-%m-%d")
    for day_offset in range(LOOKBACK_DAYS):
        check_date = execution_date - timedelta(days=day_offset)
        year = check_date.strftime("%Y")
        month = check_date.strftime("%m")
        day = check_date.strftime("%d")
        key = f"analytics/daily/year={year}/month={month}/day={day}/top_users.jsonl.gz"

        try:
            obj = s3_hook.get_key(key, bucket_name=_get_s3_bucket())
            if obj is None:
                continue

            import gzip

            body = obj.get()["Body"].read()
            decompressed = gzip.decompress(body).decode("utf-8")

            for line in decompressed.strip().split("\n"):
                if not line:
                    continue
                user_data = json.loads(line)
                uid = user_data.get("user_id", "unknown")
                total = user_data.get("total", 0)

                if uid not in user_totals:
                    user_totals[uid] = {
                        "user_id": uid,
                        "total_actions": 0,
                        "active_days": 0,
                        "actions_by_type": {},
                    }

                user_totals[uid]["total_actions"] += total
                user_totals[uid]["active_days"] += 1

                for action_type, count in user_data.get("actions", {}).items():
                    prev = user_totals[uid]["actions_by_type"].get(action_type, 0)
                    user_totals[uid]["actions_by_type"][action_type] = prev + count

        except Exception as exc:
            logger.debug("Could not read user data for %s: %s", check_date.isoformat(), exc)
            continue

    user_list = sorted(user_totals.values(), key=lambda x: x["total_actions"], reverse=True)
    logger.info("Aggregated activity for %d users over %d days", len(user_list), LOOKBACK_DAYS)
    return user_list


def generate_user_reports(**context):
    """Generate per-user activity summaries and overall report.

    Combines daily aggregates with per-user data to create comprehensive
    activity reports for the admin-service to serve.
    """
    ds = context["ds"]
    daily_summaries = context["ti"].xcom_pull(task_ids="query_analytics_aggregates") or []
    user_activities = context["ti"].xcom_pull(task_ids="query_per_user_activity") or []

    report = _build_user_activity_report(ds, daily_summaries, user_activities)

    context["ti"].xcom_push(key="report", value=report)
    context["ti"].xcom_push(key="user_count", value=len(user_activities))
    return report


def _build_user_activity_report(ds, daily_summaries, user_activities):
    """Build the user activity report - separated for testability."""
    # Compute trend metrics
    total_events = sum(d.get("total_events", 0) for d in daily_summaries)
    total_users = max((d.get("active_users", 0) for d in daily_summaries), default=0)

    avg_daily_events = total_events / len(daily_summaries) if daily_summaries else 0

    return {
        "report_type": "user_activity",
        "report_date": ds,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "lookback_days": LOOKBACK_DAYS,
        "trends": {
            "total_events": total_events,
            "peak_active_users": total_users,
            "avg_daily_events": round(avg_daily_events, 2),
            "reporting_days": len(daily_summaries),
        },
        "daily_summaries": daily_summaries,
        "user_summaries": user_activities[:500],  # Cap for report size
        "top_users": user_activities[:20],
    }


def store_reports_to_s3(**context):
    """Store the generated reports to S3 for admin-service consumption.

    Writes both the full report and individual user summaries to
    well-known S3 paths that admin-service reads.
    """
    ds = context["ds"]
    report = context["ti"].xcom_pull(key="report", task_ids="generate_user_reports")
    if not report:
        logger.warning("No report to store for %s", ds)
        return

    s3_hook = S3Hook(aws_conn_id=AWS_CONN_ID)

    bucket = _get_s3_bucket()

    # Store full report
    report_key = f"{S3_REPORTS_PREFIX}/{ds}/activity_report.json"
    s3_hook.load_string(
        json.dumps(report, indent=2, default=str),
        key=report_key,
        bucket_name=bucket,
        replace=True,
    )

    # Store latest pointer for admin-service
    latest_key = f"{S3_REPORTS_PREFIX}/latest/activity_report.json"
    s3_hook.load_string(
        json.dumps(report, indent=2, default=str),
        key=latest_key,
        bucket_name=bucket,
        replace=True,
    )

    # Store per-user summaries as JSONL for individual user lookups
    user_summaries = report.get("user_summaries", [])
    if user_summaries:
        users_key = f"{S3_REPORTS_PREFIX}/{ds}/user_summaries.jsonl"
        lines = [json.dumps(u, default=str) for u in user_summaries]
        s3_hook.load_string(
            "\n".join(lines) + "\n",
            key=users_key,
            bucket_name=bucket,
            replace=True,
        )

    logger.info(
        "Stored activity report for %s: %d user summaries at s3://%s/%s",
        ds,
        len(user_summaries),
        bucket,
        report_key,
    )


with DAG(
    "otterworks_user_activity_report",
    default_args=default_args,
    description="Daily user activity report: aggregates -> per-user summaries -> S3",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["otterworks", "analytics", "reports", "etl"],
    doc_md=__doc__,
    max_active_runs=1,
) as dag:

    query_aggregates = PythonOperator(
        task_id="query_analytics_aggregates",
        python_callable=query_analytics_aggregates,
    )

    query_users = PythonOperator(
        task_id="query_per_user_activity",
        python_callable=query_per_user_activity,
    )

    generate = PythonOperator(
        task_id="generate_user_reports",
        python_callable=generate_user_reports,
    )

    store = PythonOperator(
        task_id="store_reports_to_s3",
        python_callable=store_reports_to_s3,
    )

    # Query both data sources in parallel, generate reports, store to S3
    [query_aggregates, query_users] >> generate >> store
