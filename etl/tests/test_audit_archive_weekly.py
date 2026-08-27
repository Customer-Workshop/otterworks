import gzip
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
import pytest


def _table(dynamodb):
    return dynamodb.create_table(
        TableName="otterworks-audit-events",
        KeySchema=[
            {"AttributeName": "event_id", "KeyType": "HASH"},
            {"AttributeName": "timestamp", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "event_id", "AttributeType": "S"},
            {"AttributeName": "timestamp", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


def test_audit_archives_old_events_and_deletes_in_batches(moto_aws, etl_config, load_script):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="otterworks-audit-archive")
    table = _table(boto3.resource("dynamodb", region_name="us-east-1"))
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=91)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    new = (now - timedelta(days=10)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for i in range(26):
        table.put_item(
            Item={
                "event_id": f"old-{i}",
                "timestamp": old,
                "action": "read",
                "sequence": Decimal(str(i)),
            }
        )
    for i in range(2):
        table.put_item(Item={"event_id": f"new-{i}", "timestamp": new, "action": "write"})

    load_script("audit_archive_weekly.py").main()

    ds = now.strftime("%Y-%m-%d")
    archive_key = f"audit-archive/year={ds[:4]}/week={ds}/audit_events.jsonl.gz"
    archive_metadata = s3.head_object(Bucket="otterworks-audit-archive", Key=archive_key)
    assert archive_metadata["StorageClass"] == "GLACIER"
    assert archive_metadata["ContentLength"] > 0
    s3.restore_object(
        Bucket="otterworks-audit-archive",
        Key=archive_key,
        RestoreRequest={"Days": 1},
    )
    lines = gzip.decompress(
        s3.get_object(Bucket="otterworks-audit-archive", Key=archive_key)["Body"].read()
    ).decode().strip().splitlines()
    assert len(lines) == 26
    assert all(json.loads(line)["event_id"].startswith("old-") for line in lines)
    remaining = table.scan()["Items"]
    assert {item["event_id"] for item in remaining} == {"new-0", "new-1"}
    report = json.loads(
        s3.get_object(
            Bucket="otterworks-audit-archive",
            Key=f"reports/compliance/audit-archive/{ds}/report.json",
        )["Body"].read()
    )
    assert report["results"]["events_archived"] == 26
    assert report["results"]["events_deleted_from_source"] == 26
    assert report["results"]["compressed_size_bytes"] == archive_metadata["ContentLength"]


def test_audit_empty_input_exits_zero(moto_aws, etl_config, load_script):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="otterworks-audit-archive")
    _table(boto3.resource("dynamodb", region_name="us-east-1"))
    with pytest.raises(SystemExit) as exc:
        load_script("audit_archive_weekly.py").main()
    assert exc.value.code == 0
