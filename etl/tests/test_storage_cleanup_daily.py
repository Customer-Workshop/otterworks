import json
from datetime import datetime, timezone

import boto3


def _table(dynamodb):
    return dynamodb.create_table(
        TableName="otterworks-file-metadata",
        KeySchema=[{"AttributeName": "file_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "file_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


def test_storage_cleanup_quarantines_orphans(moto_aws, etl_config, load_script):
    s3 = boto3.client("s3", region_name="us-east-1")
    for bucket in (
        "otterworks-file-storage",
        "otterworks-file-quarantine",
        "otterworks-data-lake",
    ):
        s3.create_bucket(Bucket=bucket)
    s3.put_object(Bucket="otterworks-file-storage", Key="files/referenced.txt", Body=b"keep")
    s3.put_object(Bucket="otterworks-file-storage", Key="files/orphan.txt", Body=b"orphan-data")
    s3.put_object(Bucket="otterworks-file-storage", Key="other.txt", Body=b"ignored")
    table = _table(boto3.resource("dynamodb", region_name="us-east-1"))
    table.put_item(Item={"file_id": "f1", "s3_key": "files/referenced.txt"})

    load_script("storage_cleanup_daily.py").main()

    ds = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert s3.get_object(Bucket="otterworks-file-storage", Key="files/referenced.txt")["Body"].read() == b"keep"
    assert "Contents" not in s3.list_objects_v2(Bucket="otterworks-file-storage", Prefix="files/orphan.txt")
    assert s3.get_object(
        Bucket="otterworks-file-quarantine",
        Key=f"quarantined/{ds}/files/orphan.txt",
    )["Body"].read() == b"orphan-data"
    report = json.loads(
        s3.get_object(
            Bucket="otterworks-data-lake",
            Key=f"reports/storage-cleanup/{ds}/report.json",
        )["Body"].read()
    )
    assert report["inventory"]["total_objects"] == 2
    assert report["orphans"]["orphaned_objects"] == 1
    assert report["orphans"]["orphaned_bytes"] == 11
    assert report["cleanup"]["objects_quarantined"] == 1


def test_storage_cleanup_zero_orphan_report(moto_aws, etl_config, load_script):
    s3 = boto3.client("s3", region_name="us-east-1")
    for bucket in (
        "otterworks-file-storage",
        "otterworks-file-quarantine",
        "otterworks-data-lake",
    ):
        s3.create_bucket(Bucket=bucket)
    s3.put_object(Bucket="otterworks-file-storage", Key="files/keep", Body=b"keep")
    _table(boto3.resource("dynamodb", region_name="us-east-1")).put_item(
        Item={"file_id": "f1", "s3_key": "files/keep"}
    )

    load_script("storage_cleanup_daily.py").main()

    ds = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report = json.loads(
        s3.get_object(
            Bucket="otterworks-data-lake",
            Key=f"reports/storage-cleanup/{ds}/report.json",
        )["Body"].read()
    )
    assert report["orphans"]["orphaned_objects"] == 0
    assert report["cleanup"]["objects_quarantined"] == 0
