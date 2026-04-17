"""
OtterWorks Custom Airflow Operators

Reusable operators for common OtterWorks ETL patterns.
"""

import json
import logging
from typing import Any

from airflow.models import BaseOperator
from airflow.providers.amazon.aws.hooks.dynamodb import DynamoDBHook
from airflow.providers.amazon.aws.hooks.s3 import S3Hook

logger = logging.getLogger(__name__)


class DynamoDBScanOperator(BaseOperator):
    """Scan a DynamoDB table with optional filter expression.

    Handles pagination automatically and returns all matching items.

    Args:
        table_name: DynamoDB table to scan.
        filter_expression: Optional DynamoDB filter expression string.
        expression_attribute_names: Optional attribute name aliases.
        expression_attribute_values: Optional attribute value bindings.
        projection_expression: Optional comma-separated list of attributes.
        aws_conn_id: Airflow AWS connection ID.
    """

    template_fields = (
        "table_name",
        "filter_expression",
        "expression_attribute_values",
    )

    def __init__(
        self,
        table_name: str,
        filter_expression: str | None = None,
        expression_attribute_names: dict[str, str] | None = None,
        expression_attribute_values: dict[str, Any] | None = None,
        projection_expression: str | None = None,
        aws_conn_id: str = "aws_default",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.table_name = table_name
        self.filter_expression = filter_expression
        self.expression_attribute_names = expression_attribute_names
        self.expression_attribute_values = expression_attribute_values
        self.projection_expression = projection_expression
        self.aws_conn_id = aws_conn_id

    def execute(self, context):
        hook = DynamoDBHook(
            aws_conn_id=self.aws_conn_id,
            table_name=self.table_name,
        )
        table = hook.get_conn()

        scan_kwargs = {}
        if self.filter_expression:
            scan_kwargs["FilterExpression"] = self.filter_expression
        if self.expression_attribute_names:
            scan_kwargs["ExpressionAttributeNames"] = self.expression_attribute_names
        if self.expression_attribute_values:
            scan_kwargs["ExpressionAttributeValues"] = self.expression_attribute_values
        if self.projection_expression:
            scan_kwargs["ProjectionExpression"] = self.projection_expression

        all_items = []
        while True:
            response = table.scan(**scan_kwargs)
            all_items.extend(response.get("Items", []))

            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            scan_kwargs["ExclusiveStartKey"] = last_key

        logger.info("Scanned %d items from %s", len(all_items), self.table_name)
        return all_items


class S3JsonReportOperator(BaseOperator):
    """Write a JSON report to S3.

    Serializes a dict to JSON and uploads to the specified S3 location.

    Args:
        bucket_name: Target S3 bucket.
        key: S3 object key.
        report_data_xcom_task: Task ID to pull report data from XCom.
        report_data_xcom_key: XCom key to pull report data.
        aws_conn_id: Airflow AWS connection ID.
    """

    template_fields = ("bucket_name", "key")

    def __init__(
        self,
        bucket_name: str,
        key: str,
        report_data_xcom_task: str,
        report_data_xcom_key: str = "return_value",
        aws_conn_id: str = "aws_default",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.bucket_name = bucket_name
        self.key = key
        self.report_data_xcom_task = report_data_xcom_task
        self.report_data_xcom_key = report_data_xcom_key
        self.aws_conn_id = aws_conn_id

    def execute(self, context):
        report_data = context["ti"].xcom_pull(
            task_ids=self.report_data_xcom_task,
            key=self.report_data_xcom_key,
        )
        if not report_data:
            logger.warning("No report data to write")
            return None

        s3_hook = S3Hook(aws_conn_id=self.aws_conn_id)
        s3_hook.load_string(
            json.dumps(report_data, indent=2, default=str),
            key=self.key,
            bucket_name=self.bucket_name,
            replace=True,
        )

        logger.info("Wrote report to s3://%s/%s", self.bucket_name, self.key)
        return f"s3://{self.bucket_name}/{self.key}"
