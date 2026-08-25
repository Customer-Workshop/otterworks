"""Shared helpers for the mongo_files workload (DynamoDB file metadata -> Atlas).

The file-service's metadata has lived in the shared DynamoDB table
`otterworks-file-metadata` since the platform's early days, namespaced by an
`ns` attribute. This module holds the pieces the migration and the recon share:
connection/config resolution, the fully paginated source scan, the
item-to-document mapping (including the quarantine rules), and the
order-independent checksum used by the estate's own manifests.

Nothing here reads wall-clock time and no identifier is random: document ids
are `uuid5` of the source key, so a rerun reproduces byte-identical documents.
"""

import hashlib
import os
import uuid
from datetime import datetime, timezone

from bson import Binary, Int64

# Namespace for deterministic document ids: uuid5(URL-namespace, workload url).
ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://otterworks.app/mongo_files")

DYNAMO_TABLE = "otterworks-file-metadata"

# Attributes the file-service has always written, and where they land.
FIELD_MAP = {
    "id": "legacy_id",
    "ns": "tenant",
    "name": "name",
    "mime_type": "mime_type",
    "size_bytes": "size_bytes",
    "s3_key": "storage_key",
    "folder_id": "folder_id",
    "owner_id": "owner_id",
    "version": "version",
    "is_trashed": "is_trashed",
    "created_at": "created_at",
    "updated_at": "modified_at",
}

# Attributes carried as BSON dates rather than the legacy ISO-8601 strings.
DATE_ATTRS = {"created_at", "updated_at"}

QUARANTINE_REASONS = (
    "missing_tenant",
    "missing_storage_key",
    "missing_timestamp",
    "invalid_encoding",
    "invalid_timestamp",
)


def db_names(ns: str) -> tuple[str, str]:
    return f"ow_tp_mongodb_{ns}", f"ow_tp_mongodb_{ns}_quarantine"


COLLECTION = "files"
QUARANTINE_COLLECTION = "files_quarantine"


def mongo_uri() -> str:
    """Fixture URI by default; the live Atlas URI only when asked explicitly."""
    if os.getenv("MONGO_FILES_TARGET", "fixture") == "live":
        uri = os.getenv("MONGODB_ATLAS_URI")
        if not uri:
            raise SystemExit("MONGO_FILES_TARGET=live requires MONGODB_ATLAS_URI")
        return uri
    return os.getenv("MONGO_FILES_FIXTURE_URI", "mongodb://localhost:27018")


def run_mode() -> str:
    return "live" if os.getenv("MONGO_FILES_TARGET", "fixture") == "live" else "fixture"


def dynamo_client():
    import boto3

    return boto3.client(
        "dynamodb",
        endpoint_url=os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566"),
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
    )


def doc_id(source_key: str) -> str:
    """Deterministic document id: uuid5 of the DynamoDB partition key."""
    return str(uuid.uuid5(ID_NAMESPACE, source_key))


class Checksum:
    """Order-independent checksum over a set of lines (md5 digests summed).

    Mirrors the estate's own manifest checksum so a value recomputed from the
    document store is directly comparable with the legacy store's.
    """

    _MOD = 1 << 128

    def __init__(self) -> None:
        self._total = 0
        self.count = 0

    def add(self, line: str) -> None:
        digest = hashlib.md5(line.encode()).digest()
        self._total = (self._total + int.from_bytes(digest, "big")) % self._MOD
        self.count += 1

    def hexdigest(self) -> str:
        return f"{self._total:032x}"


def utf8_or_none(value: str) -> bytes | None:
    """Return the UTF-8 bytes of `value`, or None when it is not valid UTF-8.

    DynamoDB S attributes are declared UTF-8, but bytes written by the oldest
    file-service releases can survive as lone surrogates; those must never be
    silently repaired.
    """
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError:
        return None


def raw_hex(value: str) -> str:
    return value.encode("utf-8", "surrogatepass").hex()


def parse_legacy_timestamp(value: str) -> datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def is_orphaned(storage_key: str, tenant: str) -> bool:
    """True when the storage key names no owning object in the files bucket.

    Live keys are `<ns>/files/<owner>/<uuid>`; anything else under the tenant
    prefix has no owning document behind it.
    """
    parts = storage_key.split("/")
    return not (len(parts) >= 2 and parts[0] == tenant and parts[1] == "files")


def _scalar(attr: dict):
    """Map a single DynamoDB attribute value to its BSON counterpart."""
    (kind, raw), = attr.items()
    if kind == "S":
        return raw
    if kind == "N":
        return Int64(raw) if "." not in raw and "e" not in raw.lower() else float(raw)
    if kind == "BOOL":
        return bool(raw)
    if kind == "B":
        return Binary(raw)
    if kind == "NULL":
        return None
    if kind == "L":
        # A list member's position is part of its meaning, so a NULL member is
        # kept in place rather than collapsing the list around it.
        return [_scalar(v) for v in raw]
    if kind == "M":
        # Map keys are attributes: a NULL one is omitted, as at the top level.
        return {k: s for k, v in raw.items() if (s := _scalar(v)) is not None}
    if kind in ("SS", "NS", "BS"):
        return [_scalar({kind[0]: v}) for v in raw]
    raise ValueError(f"unsupported DynamoDB attribute type: {kind}")


def transform(item: dict) -> tuple[dict | None, dict | None]:
    """Map one DynamoDB item to (document, quarantine_document).

    Exactly one of the two is returned. Required attributes are never
    defaulted: a missing tenant, storage key or timestamp quarantines the item
    with a reason code, as does a storage key or filename that is not valid
    UTF-8. Unknown attributes are preserved under `extras`.
    """
    source_key = item.get("id", {}).get("S")

    def quarantine(reason: str, detail: dict | None = None) -> tuple[None, dict]:
        doc = {
            "_id": doc_id(source_key) if source_key else doc_id(repr(sorted(item))),
            "reason": reason,
            "source_table": DYNAMO_TABLE,
            "source_key": source_key,
            "raw_item": {k: _summarize(v) for k, v in item.items()},
        }
        if detail:
            doc.update(detail)
        return None, doc

    if source_key is None:
        return quarantine("missing_storage_key")

    tenant = item.get("ns", {}).get("S")
    if not tenant:
        return quarantine("missing_tenant")

    storage_key = item.get("s3_key", {}).get("S")
    if not storage_key:
        return quarantine("missing_storage_key")

    for attr in ("s3_key", "name"):
        value = item.get(attr, {}).get("S")
        if value is not None and utf8_or_none(value) is None:
            return quarantine(
                "invalid_encoding",
                {"invalid_attribute": attr, "raw_bytes_hex": raw_hex(value)},
            )

    doc: dict = {"_id": doc_id(source_key)}
    for attr, value in item.items():
        target = FIELD_MAP.get(attr)
        if target is None:
            extra = _scalar(value)
            if extra is not None:  # a NULL attribute is absent, never a null
                doc.setdefault("extras", {})[attr] = extra
            continue
        if attr in DATE_ATTRS:
            text = value.get("S")
            if not text:
                return quarantine("missing_timestamp", {"invalid_attribute": attr})
            parsed = parse_legacy_timestamp(text)
            if parsed is None:
                return quarantine(
                    "invalid_timestamp",
                    {"invalid_attribute": attr, "raw_value": text},
                )
            doc[target] = parsed
            continue
        mapped = _scalar(value)
        if mapped is None:  # a NULL attribute is an absent attribute, not a null
            continue
        doc[target] = mapped

    if "modified_at" not in doc:
        return quarantine("missing_timestamp", {"invalid_attribute": "updated_at"})

    doc["orphaned_metadata"] = is_orphaned(doc["storage_key"], tenant)
    return doc, None


def _summarize(attr: dict):
    """Quarantine copies keep the raw attribute, binary-safe and lossless."""
    (kind, raw), = attr.items()
    if kind == "S":
        return raw if utf8_or_none(raw) is not None else {"hex": raw_hex(raw)}
    if kind == "B":
        return Binary(raw)
    return _scalar(attr)


def scan_pages(ns: str, projection: str | None = None):
    """Yield every page of the ns-filtered source scan, fully paginated."""
    client = dynamo_client()
    kwargs = {
        "TableName": DYNAMO_TABLE,
        "FilterExpression": "#n = :ns",
        "ExpressionAttributeNames": {"#n": "ns"},
        "ExpressionAttributeValues": {":ns": {"S": ns}},
    }
    if projection:
        kwargs["ProjectionExpression"] = projection
    while True:
        resp = client.scan(**kwargs)
        yield resp.get("Items", [])
        last = resp.get("LastEvaluatedKey")
        if not last:
            return
        kwargs["ExclusiveStartKey"] = last
