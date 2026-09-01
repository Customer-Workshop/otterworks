#!/usr/bin/env python3
"""App-side replacement for the CUSTOMER_MASTER triggers and sequences.

Replaces TRG_CUSTOMER_MASTER_SEQ, TRG_CUSTOMER_MASTER_HIST,
TRG_ENTITY_ATTR_VALUE_SEQ, SEQ_CUSTOMER_MASTER, SEQ_CUSTOMER_MASTER_HIST and
SEQ_ENTITY_ATTR_VALUE (services/legacy-billing/db/oracle/schema/02_horror.sql).
The derivations are pure functions; only CustomerWritePath touches MongoDB.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from bson import Int64, ObjectId

NS_VALUE = "mongo_032752"
TARGET_DB = "ow_tp_mongodb_032752"
CUSTOMERS = "customers"
HISTORY = "customer_master_hist"
HISTORY_OPS = ("UPD", "DEL")
EMBED_ARRAY_PATH = "attributes"
REPO_ROOT = Path(__file__).resolve().parents[1].parent
MAPPING_SPEC = REPO_ROOT / ".migration/03_mapping_spec.json"

# NLS_DATE_LANGUAGE=ENGLISH month abbreviations: TO_CHAR(SYSDATE, 'DD-MON-YY ...')
# must not depend on the process locale.
MONTH_ABBREVIATIONS = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)


def history_fields(spec_path: Path = MAPPING_SPEC) -> list[str]:
    """Target field names of customer_master_hist, per the approved mapping spec."""
    spec = json.loads(spec_path.read_text())
    for entry in spec.get("collections", []):
        if entry["collection"] == HISTORY:
            return [field["target"] for field in entry["fields"]]
    raise RuntimeError(f"mapping spec {spec_path} has no '{HISTORY}' entry")


def app_cust_seq_no() -> Int64:
    """Monotonic app-generated stand-in for SEQ_CUSTOMER_MASTER.NEXTVAL."""
    return Int64(time.time_ns() // 1000)


def derive_on_insert(doc: dict) -> dict:
    """TRG_CUSTOMER_MASTER_SEQ: id, upper-cased name, row version, sequence number."""
    derived = dict(doc)
    if derived.get("_id") is None:
        derived["_id"] = str(uuid.uuid4())
    cust_name = derived.get("cust_name")
    derived["cust_name_upper"] = None if cust_name is None else cust_name.upper()
    derived["row_version_no"] = derived.get("row_version_no") or 1
    if derived.get("cust_seq_no") is None:
        derived["cust_seq_no"] = app_cust_seq_no()
    derived["ns"] = NS_VALUE
    return derived


def hist_dt_string(now) -> str:
    """TO_CHAR(SYSDATE, 'DD-MON-YY HH24:MI:SS') with NLS_DATE_LANGUAGE=ENGLISH."""
    return (
        f"{now.day:02d}-{MONTH_ABBREVIATIONS[now.month - 1]}-{now.year % 100:02d} "
        f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"
    )


def history_doc(old_doc: dict, op: str, now, fields: list[str] | None = None) -> dict:
    """TRG_CUSTOMER_MASTER_HIST: full-row copy of the pre-image into the audit collection."""
    if op not in HISTORY_OPS:
        raise ValueError(f"hist_op must be one of {HISTORY_OPS}: {op}")
    field_names = history_fields() if fields is None else fields
    document = {"_id": ObjectId()}
    for name in field_names:
        if name == "cust_id":
            document[name] = old_doc.get("_id")
        elif name == "hist_op":
            document[name] = op
        elif name == "hist_dt":
            document[name] = hist_dt_string(now)
        else:
            document[name] = old_doc.get(name)
    document["ns"] = NS_VALUE
    return document


def next_attribute(
    existing_elements, attr_name, attr_value, attr_type, created_dt
) -> dict:
    """TRG_ENTITY_ATTR_VALUE_SEQ: elements are keyed by attr_name, eav_id preserved."""
    element = {
        "attr_name": attr_name,
        "attr_value": attr_value,
        "attr_type": attr_type,
        "created_dt": created_dt,
    }
    for existing in existing_elements or []:
        if existing.get("attr_name") == attr_name and existing.get("eav_id") is not None:
            element["eav_id"] = existing["eav_id"]
            break
    return element


class CustomerWritePath:
    """Customer mutations with the trigger-equivalent history write.

    update() and delete() write the history document inside the same client
    session/transaction as the customer mutation. Transactions require a replica
    set or sharded deployment; on a standalone deployment pymongo raises
    OperationFailure and the caller sees it — failures are never swallowed, and
    there is no silent sequential fallback that could lose the audit row.
    """

    def __init__(self, db):
        if db.name != TARGET_DB:
            raise ValueError(f"write path is restricted to {TARGET_DB}: got {db.name}")
        self.db = db
        self.customers = db[CUSTOMERS]
        self.history = db[HISTORY]

    def insert(self, doc: dict) -> dict:
        document = derive_on_insert(doc)
        self.customers.insert_one(document)
        return document

    def update(self, cust_id, changes: dict, now=None) -> dict:
        now = self._now(now)
        with self.db.client.start_session() as session:
            with session.start_transaction():
                old_doc = self.customers.find_one({"_id": cust_id}, session=session)
                if old_doc is None:
                    raise KeyError(f"no customer with _id {cust_id}")
                update = dict(changes)
                update["row_version_no"] = (old_doc.get("row_version_no") or 0) + 1
                if "cust_name" in changes:
                    cust_name = changes["cust_name"]
                    update["cust_name_upper"] = (
                        None if cust_name is None else cust_name.upper()
                    )
                update["ns"] = NS_VALUE
                self.history.insert_one(
                    history_doc(old_doc, "UPD", now), session=session
                )
                self.customers.update_one(
                    {"_id": cust_id}, {"$set": update}, session=session
                )
        return update

    def delete(self, cust_id, now=None) -> dict:
        now = self._now(now)
        with self.db.client.start_session() as session:
            with session.start_transaction():
                old_doc = self.customers.find_one({"_id": cust_id}, session=session)
                if old_doc is None:
                    raise KeyError(f"no customer with _id {cust_id}")
                document = history_doc(old_doc, "DEL", now)
                self.history.insert_one(document, session=session)
                self.customers.delete_one({"_id": cust_id}, session=session)
        return document

    def put_attribute(self, cust_id, attr_name, attr_value, attr_type, created_dt) -> dict:
        old_doc = self.customers.find_one({"_id": cust_id})
        if old_doc is None:
            raise KeyError(f"no customer with _id {cust_id}")
        elements = list(old_doc.get(EMBED_ARRAY_PATH) or [])
        element = next_attribute(elements, attr_name, attr_value, attr_type, created_dt)
        remaining = [
            existing for existing in elements if existing.get("attr_name") != attr_name
        ]
        self.customers.update_one(
            {"_id": cust_id},
            {"$set": {EMBED_ARRAY_PATH: remaining + [element]}},
        )
        return element

    @staticmethod
    def _now(now):
        if now is not None:
            return now
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
