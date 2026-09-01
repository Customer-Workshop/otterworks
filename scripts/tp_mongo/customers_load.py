"""Wave 1 loader: OW_BILLING.CUSTOMER_MASTER + ENTITY_ATTR_VALUE -> ow_tp_demo.customers.

Reads the legacy estate with SELECTs only, canonicalizes at load time (the mapping's rules,
applied here rather than in recon), embeds each customer's EAV rows as `attributes[]`, and
writes one document per source row keyed by the natural business key `CUST_NO`.

Anomalies follow the STOP B policy, field-scoped: the customer is always loaded, the raw
legacy value is always preserved under `legacy.*`, the typed field is omitted, and a record
naming the customer and the field is written to the quarantine database.

Idempotent: every run clears this namespace's documents from the collections it owns and
reloads them, so a retry starts clean.

    python3 scripts/tp_mongo/customers_load.py --ns demo \
        --source-dsn-secret OW_BILLING_SOURCE_DSN --target-uri-secret MONGODB_ATLAS_URI \
        --target-db ow_tp_demo --quarantine-db ow_tp_demo_quarantine
"""

from __future__ import annotations

import argparse
import datetime as dt
import decimal
import json
import re
import sys
from pathlib import Path

from bson.decimal128 import Decimal128
from pymongo import ASCENDING, InsertOne

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import mongo_database, ns_batch_no, oracle_connect  # noqa: E402

UNIT = "customers"
ROOT_TABLE = "OW_BILLING.CUSTOMER_MASTER"
EAV_TABLE = "OW_BILLING.ENTITY_ATTR_VALUE"
BATCH_SIZE = 1000

MAPPING_SPEC = Path(".migration/03_mapping_spec.json")

# Typed fields derived from the estate's `DD-MON-YY` string dates (D4).
DERIVED_DATES = [("SIGNUP_DT", "signup_at"), ("LAST_ACTIVITY_DT", "last_activity_at")]

# Delimited lists parsed into arrays; a token that does not match is dropped from the array
# and reported, never coerced (D5).
DERIVED_LISTS = [("RELATED_ACCT_IDS", "related_acct_ids", re.compile(r"^[0-9]{1,12}$")),
                 ("PROMO_CODES_CSV", "promo_codes", re.compile(r"^[A-Z0-9]{2,20}$"))]

MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}


def parse_legacy_date(raw: str) -> dt.datetime | None:
    """`DD-MON-YY` under Oracle's RR windowing (00-49 -> 2000s, 50-99 -> 1900s).

    Returns None for anything the estate itself cannot convert, including calendar-invalid
    days like `31-FEB-24`.
    """
    parts = raw.strip().upper().split("-")
    if len(parts) != 3:
        return None
    day, mon, year = parts
    if not day.isdigit() or not year.isdigit() or mon not in MONTHS:
        return None
    century = 2000 if int(year) <= 49 else 1900
    try:
        return dt.datetime(century + int(year), MONTHS[mon], int(day),
                           tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def load_fields(spec_path: Path) -> list[tuple[str, str, str, list[str]]]:
    """`(source column, target path, bson type, rules)` for this unit's collection, straight
    from the approved mapping spec — the loader and recon read the same rule list, so a
    field can never be canonicalized one way at load time and compared another way."""
    spec = json.loads(spec_path.read_text())
    collections = [c for c in spec["collections"] if c["collection"] == UNIT]
    if not collections:
        raise SystemExit(f"mapping spec {spec_path} has no '{UNIT}' collection")
    return [(f["source"], f["target"], f["bson_type"], list(f["rules"]))
            for f in collections[0]["fields"]]


def canonical(value, bson_type: str, rules: list[str]):
    """Load-time canonicalization: exactly the mapping's rules for this field, in order.

    Only the CHAR columns carry `rstrip_spaces`; blank-stripping a VARCHAR2 would rewrite
    source data (the estate stores meaningful all-blank legacy date strings).
    """
    if isinstance(value, str):
        if "rstrip_spaces" in rules:
            value = value.rstrip(" ")
        if "empty_string_is_null" in rules and value == "":
            return None
    if value is None:
        return None
    if bson_type == "decimal":
        return Decimal128(value if isinstance(value, decimal.Decimal)
                          else decimal.Decimal(str(value)))
    if bson_type == "long":
        return int(value)
    if bson_type == "date":
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc).replace(
            microsecond=(value.microsecond // 1000) * 1000)
    return value


def put(doc: dict, path: str, value) -> None:
    head, _, tail = path.partition(".")
    if tail:
        doc.setdefault(head, {})[tail] = value
    else:
        doc[head] = value


def fetch_attributes(cursor, batch_no: int) -> dict[str, list[dict]]:
    """EAV rows for this batch's customers, embedded as an ordered array.

    An array rather than a map: the estate holds duplicate `(entity, attr_name)` pairs, so a
    keyed object would silently drop values (D2).
    """
    cursor.execute(
        f"SELECT e.ENTITY_ID, e.ATTR_NAME, e.ATTR_VALUE, e.ATTR_TYPE, e.CREATED_DT "
        f"  FROM {EAV_TABLE} e "
        f" WHERE e.ENTITY_TYPE = 'CUSTOMER' "
        f"   AND EXISTS (SELECT 1 FROM {ROOT_TABLE} c "
        f"                WHERE c.CUST_ID = e.ENTITY_ID AND c.CONVERSION_BATCH_NO = :b) "
        f" ORDER BY e.ENTITY_ID, e.EAV_ID", b=batch_no)
    by_entity: dict[str, list[dict]] = {}
    for entity_id, name, value, attr_type, created_dt in cursor:
        by_entity.setdefault(entity_id, []).append({
            "name": name, "value": value, "type": attr_type,
            "legacy": {"created_dt": created_dt},
        })
    return by_entity


def build_document(row: dict, fields, attributes: list[dict], ns: str) -> tuple[dict, list[dict]]:
    doc: dict = {"ns": ns}
    quarantine: list[dict] = []
    for column, target, bson_type, rules in fields:
        put(doc, target, canonical(row[column], bson_type, rules))

    for column, target in DERIVED_DATES:
        raw = row[column]
        if raw is None or raw.strip() == "":
            continue
        parsed = parse_legacy_date(raw)
        if parsed is None:
            quarantine.append({"field": column, "reason": "unparseable_legacy_date",
                               "raw_value": raw})
        else:
            doc[target] = parsed

    for column, target, token_re in DERIVED_LISTS:
        raw = row[column]
        if raw is None or raw.strip() == "":
            continue
        tokens = [t.strip() for t in raw.split(",")]
        kept = [t for t in tokens if token_re.match(t)]
        doc[target] = kept
        if len(kept) != len([t for t in tokens if t != ""]) or "" in tokens:
            quarantine.append({"field": column, "reason": "malformed_delimited_list",
                               "raw_value": raw, "tokens_kept": kept})

    doc["attributes"] = attributes
    for q in quarantine:
        q.update({"_id": f"{ns}:{doc['_id']}:{q['field']}", "ns": ns, "unit": UNIT,
                  "cust_no": doc["_id"], "cust_id": doc["cust_id"]})
    return doc, quarantine


def ensure_indexes(collection) -> None:
    """D9's index plan for `customers`, including D6's collation index, which replaces the
    trigger-maintained `CUST_NAME_UPPER` shadow column as the case-insensitive lookup path."""
    collection.create_index([("cust_id", ASCENDING)], name="cust_id_unique", unique=True)
    collection.create_index([("conversion_batch_no", ASCENDING)], name="conversion_batch_no")
    collection.create_index([("tenant_id", ASCENDING), ("status_cd", ASCENDING)],
                            name="tenant_status")
    collection.create_index([("cust_name", ASCENDING)], name="cust_name_ci",
                            collation={"locale": "en", "strength": 2})


def seed_counter(db, cursor, ns: str) -> int:
    """`CUST_SEQ_NO` is trigger-assigned from SEQ_CUSTOMER_MASTER source-side; new inserts on
    Atlas draw from a counters document instead (D3), seeded past the sequence's high-water
    mark so no number is ever reissued."""
    cursor.execute("SELECT last_number FROM all_sequences "
                   "WHERE sequence_owner = 'OW_BILLING' AND sequence_name = 'SEQ_CUSTOMER_MASTER'")
    row = cursor.fetchone()
    if row is None:
        raise SystemExit("SEQ_CUSTOMER_MASTER not found; D3's counter cannot be seeded")
    seq = int(row[0])
    db["counters"].replace_one({"_id": f"{ns}:customers.cust_seq_no"},
                               {"_id": f"{ns}:customers.cust_seq_no", "ns": ns,
                                "unit": UNIT, "seq": seq}, upsert=True)
    return seq


def load(ns: str, source_dsn_secret: str, target_uri_secret: str, target_db: str,
         quarantine_db: str, spec_path: Path = MAPPING_SPEC) -> dict:
    batch_no = ns_batch_no(ns)
    fields = load_fields(spec_path)
    db = mongo_database(target_uri_secret, target_db)
    qdb = mongo_database(target_uri_secret, quarantine_db)
    customers, quarantined = db["customers"], qdb["customers"]

    connection = oracle_connect(source_dsn_secret)
    with connection, connection.cursor() as cursor:
        cursor.arraysize = BATCH_SIZE
        attributes = fetch_attributes(cursor, batch_no)
        counter_seed = seed_counter(db, cursor, ns)

        columns = [f[0] for f in fields]
        cursor.execute(f"SELECT {', '.join(columns)} FROM {ROOT_TABLE} "
                       f" WHERE CONVERSION_BATCH_NO = :b ORDER BY CUST_NO", b=batch_no)
        names = [d[0] for d in cursor.description]

        # A retry starts clean: this namespace's slice is removed before it is rewritten.
        customers.delete_many({"ns": ns})
        quarantined.delete_many({"ns": ns, "unit": UNIT})

        loaded = embedded = 0
        docs: list[InsertOne] = []
        quarantine_docs: list[InsertOne] = []
        for row in cursor:
            record = dict(zip(names, row))
            doc, quarantine = build_document(record, fields,
                                             attributes.get(record["CUST_ID"], []), ns)
            embedded += len(doc["attributes"])
            docs.append(InsertOne(doc))
            quarantine_docs.extend(InsertOne(q) for q in quarantine)
            if len(docs) >= BATCH_SIZE:
                customers.bulk_write(docs, ordered=False)
                loaded += len(docs)
                docs = []
        if docs:
            customers.bulk_write(docs, ordered=False)
            loaded += len(docs)
        if quarantine_docs:
            quarantined.bulk_write(quarantine_docs, ordered=False)

    ensure_indexes(customers)
    reasons: dict[str, int] = {}
    for q in quarantined.find({"ns": ns, "unit": UNIT}, {"reason": 1}):
        reasons[q["reason"]] = reasons.get(q["reason"], 0) + 1
    return {"unit": UNIT, "ns": ns, "batch_no": batch_no,
            "target": f"{target_db}.customers", "loaded": loaded,
            "embedded_attributes": embedded,
            "quarantine_target": f"{quarantine_db}.customers",
            "quarantined": sum(reasons.values()), "quarantine_by_reason": reasons,
            "counters_seed": counter_seed}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="customers_load")
    p.add_argument("--ns", default="demo")
    p.add_argument("--source-dsn-secret", required=True,
                   help="ENV VAR NAME holding the read-only source DSN")
    p.add_argument("--target-uri-secret", required=True,
                   help="ENV VAR NAME holding the migration-cluster URI")
    p.add_argument("--target-db", required=True)
    p.add_argument("--quarantine-db", required=True)
    p.add_argument("--mapping", type=Path, default=MAPPING_SPEC)
    args = p.parse_args(argv)
    print(json.dumps(load(args.ns, args.source_dsn_secret, args.target_uri_secret,
                          args.target_db, args.quarantine_db, args.mapping), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
