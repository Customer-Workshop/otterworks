# aws_owner.py - Resolve the expected AWS S3 bucket owner

import os

import boto3


def resolve_expected_bucket_owner(config, aws_access_key, aws_secret_key, aws_region):
    """Return the AWS account ID expected to own the ETL S3 buckets.

    Resolution order: config.ini [aws] account_id, the AWS_ACCOUNT_ID environment
    variable, then the account the ETL credentials themselves belong to (STS).
    """
    account_id = config.get("aws", "account_id", fallback="").strip()
    if not account_id:
        account_id = os.environ.get("AWS_ACCOUNT_ID", "").strip()
    if not account_id:
        sts_client = boto3.client(
            "sts",
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region,
        )
        account_id = str(sts_client.get_caller_identity().get("Account", "")).strip()
    if not account_id:
        raise RuntimeError("Unable to resolve the expected S3 bucket owner AWS account ID")
    return account_id
