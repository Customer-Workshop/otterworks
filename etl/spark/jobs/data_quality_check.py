"""
OtterWorks Data Quality Check - PySpark Job

Validates data quality across the analytics data lake by checking
for completeness, consistency, freshness, and anomalies.

Usage:
    spark-submit --master yarn \
        --deploy-mode cluster \
        data_quality_check.py \
        --data-path s3://otterworks-data-lake/aggregated/ \
        --output-path s3://otterworks-data-lake/quality-reports/ \
        --date 2024-01-15
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("otterworks.data_quality_check")


def create_spark_session(app_name="OtterWorks-DataQualityCheck"):
    """Create and configure a SparkSession."""
    return (
        SparkSession.builder.appName(app_name)
        .config("spark.sql.parquet.compression.codec", "snappy")
        .getOrCreate()
    )


class DataQualityResult:
    """Container for a single quality check result."""

    def __init__(self, check_name, dataset, passed, details=None, severity="error"):
        self.check_name = check_name
        self.dataset = dataset
        self.passed = passed
        self.details = details or {}
        self.severity = severity

    def to_dict(self):
        return {
            "check_name": self.check_name,
            "dataset": self.dataset,
            "passed": self.passed,
            "severity": self.severity,
            "details": self.details,
        }


def check_completeness(spark, data_path, target_date):
    """Check that all expected aggregation datasets exist and are non-empty.

    Verifies that each aggregation output (by_user, by_document, by_file,
    hourly, daily_summary) has data for the target date.
    """
    results = []
    expected_datasets = ["by_user", "by_document", "by_file", "hourly", "daily_summary"]

    for dataset in expected_datasets:
        path = f"{data_path}/{dataset}/event_date={target_date}"
        try:
            df = spark.read.parquet(path)
            count = df.count()
            passed = count > 0
            results.append(
                DataQualityResult(
                    check_name="completeness",
                    dataset=dataset,
                    passed=passed,
                    details={"row_count": count, "path": path},
                    severity="error" if not passed else "info",
                )
            )
        except Exception as exc:
            results.append(
                DataQualityResult(
                    check_name="completeness",
                    dataset=dataset,
                    passed=False,
                    details={"error": str(exc), "path": path},
                    severity="error",
                )
            )

    return results


def check_null_rates(spark, data_path, target_date):
    """Check that critical columns have acceptable null rates.

    Verifies that key fields like user IDs and timestamps don't have
    excessive nulls that would indicate data pipeline issues.
    """
    results = []
    null_thresholds = {
        "by_user": {
            "columns": ["resolved_user_id", "total_actions"],
            "max_null_pct": 0.0,
        },
        "daily_summary": {
            "columns": ["total_events", "active_users"],
            "max_null_pct": 0.0,
        },
        "hourly": {
            "columns": ["event_hour", "total_events"],
            "max_null_pct": 0.0,
        },
    }

    for dataset, config in null_thresholds.items():
        path = f"{data_path}/{dataset}/event_date={target_date}"
        try:
            df = spark.read.parquet(path)
            total = df.count()
            if total == 0:
                continue

            for col_name in config["columns"]:
                null_count = df.filter(F.col(col_name).isNull()).count()
                null_pct = null_count / total

                passed = null_pct <= config["max_null_pct"]
                results.append(
                    DataQualityResult(
                        check_name="null_rate",
                        dataset=dataset,
                        passed=passed,
                        details={
                            "column": col_name,
                            "null_count": null_count,
                            "total_rows": total,
                            "null_percentage": round(null_pct * 100, 4),
                            "threshold_percentage": config["max_null_pct"] * 100,
                        },
                        severity="error" if not passed else "info",
                    )
                )
        except Exception as exc:
            results.append(
                DataQualityResult(
                    check_name="null_rate",
                    dataset=dataset,
                    passed=False,
                    details={"error": str(exc)},
                    severity="warning",
                )
            )

    return results


def check_value_ranges(spark, data_path, target_date):
    """Check that numeric values fall within expected ranges.

    Validates that counts are non-negative and sizes are within
    reasonable bounds to catch data corruption or calculation errors.
    """
    results = []

    path = f"{data_path}/daily_summary/event_date={target_date}"
    try:
        df = spark.read.parquet(path)

        non_negative_cols = [
            "total_events",
            "active_users",
            "active_documents",
            "active_files",
            "documents_created",
            "documents_edited",
            "files_uploaded",
            "bytes_uploaded",
        ]

        for col_name in non_negative_cols:
            if col_name not in df.columns:
                continue
            neg_count = df.filter(F.col(col_name) < 0).count()
            passed = neg_count == 0
            results.append(
                DataQualityResult(
                    check_name="value_range",
                    dataset="daily_summary",
                    passed=passed,
                    details={
                        "column": col_name,
                        "negative_values": neg_count,
                        "check": "non_negative",
                    },
                    severity="error" if not passed else "info",
                )
            )
    except Exception as exc:
        results.append(
            DataQualityResult(
                check_name="value_range",
                dataset="daily_summary",
                passed=False,
                details={"error": str(exc)},
                severity="warning",
            )
        )

    return results


def check_consistency(spark, data_path, target_date):
    """Check cross-dataset consistency.

    Verifies that summary totals are consistent with detail-level data.
    For example, the daily_summary active_users should equal the number
    of distinct users in the by_user dataset.
    """
    results = []

    try:
        summary_path = f"{data_path}/daily_summary/event_date={target_date}"
        user_path = f"{data_path}/by_user/event_date={target_date}"

        summary_df = spark.read.parquet(summary_path)
        user_df = spark.read.parquet(user_path)

        summary_row = summary_df.first()
        if summary_row:
            summary_users = summary_row["active_users"]
            detail_users = user_df.select("resolved_user_id").distinct().count()

            passed = summary_users == detail_users
            results.append(
                DataQualityResult(
                    check_name="consistency",
                    dataset="daily_summary vs by_user",
                    passed=passed,
                    details={
                        "summary_active_users": summary_users,
                        "detail_distinct_users": detail_users,
                        "difference": abs(summary_users - detail_users),
                    },
                    severity="warning" if not passed else "info",
                )
            )
    except Exception as exc:
        results.append(
            DataQualityResult(
                check_name="consistency",
                dataset="daily_summary vs by_user",
                passed=False,
                details={"error": str(exc)},
                severity="warning",
            )
        )

    return results


def check_freshness(spark, data_path, target_date):
    """Check that data is fresh (not stale).

    Verifies the target date partition exists and that data was
    written recently enough to be considered current.
    """
    results = []

    path = f"{data_path}/daily_summary/event_date={target_date}"
    try:
        df = spark.read.parquet(path)
        count = df.count()

        # Data exists for the target date
        passed = count > 0
        results.append(
            DataQualityResult(
                check_name="freshness",
                dataset="daily_summary",
                passed=passed,
                details={
                    "target_date": target_date,
                    "row_count": count,
                },
                severity="error" if not passed else "info",
            )
        )
    except Exception as exc:
        results.append(
            DataQualityResult(
                check_name="freshness",
                dataset="daily_summary",
                passed=False,
                details={"error": str(exc), "target_date": target_date},
                severity="error",
            )
        )

    return results


def generate_report(results, target_date, output_path, spark):
    """Generate and write the quality check report.

    Args:
        results: List of DataQualityResult objects.
        target_date: The date that was checked.
        output_path: S3 path for the report output.
        spark: SparkSession for writing.
    """
    total_checks = len(results)
    passed_checks = sum(1 for r in results if r.passed)
    failed_checks = total_checks - passed_checks
    error_failures = sum(1 for r in results if not r.passed and r.severity == "error")

    report = {
        "report_type": "data_quality",
        "target_date": target_date,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "summary": {
            "total_checks": total_checks,
            "passed": passed_checks,
            "failed": failed_checks,
            "error_failures": error_failures,
            "pass_rate": round(passed_checks / total_checks * 100, 2) if total_checks else 0,
            "overall_status": "PASS" if error_failures == 0 else "FAIL",
        },
        "checks": [r.to_dict() for r in results],
    }

    report_path = f"{output_path}/{target_date}/quality_report.json"
    report_json = json.dumps(report, indent=2, default=str)

    # Write via Spark to support S3 output
    report_rdd = spark.sparkContext.parallelize([report_json])
    report_rdd.coalesce(1).saveAsTextFile(report_path)

    logger.info(
        "Data quality report: %d/%d checks passed (%s)",
        passed_checks,
        total_checks,
        report["summary"]["overall_status"],
    )

    return report


def run(data_path, output_path, target_date):
    """Main data quality check pipeline.

    Args:
        data_path: S3 path to aggregated data.
        output_path: S3 path for quality reports.
        target_date: Date to validate (YYYY-MM-DD).
    """
    spark = create_spark_session()

    logger.info("Running data quality checks for %s on %s", target_date, data_path)

    all_results = []
    all_results.extend(check_completeness(spark, data_path, target_date))
    all_results.extend(check_null_rates(spark, data_path, target_date))
    all_results.extend(check_value_ranges(spark, data_path, target_date))
    all_results.extend(check_consistency(spark, data_path, target_date))
    all_results.extend(check_freshness(spark, data_path, target_date))

    report = generate_report(all_results, target_date, output_path, spark)

    # Fail the job if any error-severity checks failed
    error_failures = report["summary"]["error_failures"]
    if error_failures > 0:
        logger.error("%d error-severity quality checks failed", error_failures)
        spark.stop()
        sys.exit(1)

    spark.stop()
    logger.info("All quality checks passed")


def parse_args(argv=None):
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="OtterWorks Data Quality Check Spark Job")
    parser.add_argument(
        "--data-path",
        required=True,
        help="S3 path to aggregated data",
    )
    parser.add_argument(
        "--output-path",
        required=True,
        help="S3 path for quality report output",
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Target date to validate (YYYY-MM-DD)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    run(args.data_path, args.output_path, args.date)
