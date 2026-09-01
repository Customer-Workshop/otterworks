#!/usr/bin/env python3
"""Supplemental U7 evidence: PKG_OW_UTIL conversion parity and audit write-path probes.

Three stages, each writing its own artifact under .migration/recon/U7/:

  transcript  Record what the legacy package actually returns, straight from the NS=demo
              Oracle fixture. Read-only: only the four pure functions are called, never
              log_msg (which inserts). The recorded transcript is the conversion contract.
  replay      Replay the same inputs through the migrated port and compare, using the
              migrated `codes` collection for the lookup path.
  probes      Exercise the migrated audit write path (TTL index and expiry, autonomous
              independence under an aborted caller transaction, truncation, silent
              failure). Probe documents are cleaned up; the next load run drops and
              recreates the collection regardless.

The harness verdict is the merge authority; nothing here self-certifies the unit.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1].parent
APP_DIR = REPO_ROOT / "services/legacy-billing/app"
OUT_DIR = REPO_ROOT / ".migration/recon/U7"

NS_VALUE = "mongo_032752"
TARGET_DB = "ow_tp_mongodb_032752"
AUDIT_COLLECTION = "billing_audit_log"
CODES_COLLECTION = "codes"
PROBE_MODULE = "U7-PROBE"
TTL_SECONDS = 90 * 24 * 60 * 60

# Deterministic input vectors. Each entry is (label, argument) and is replayed verbatim
# against both stacks; the code_desc vectors are extended with every (code_type, code_val)
# pair present in the fixture so the whole lookup domain is covered.
MD5_INPUTS = [
    ("empty", ""),
    ("single_char", "a"),
    ("abc", "abc"),
    ("module_name", "OW_BILLING"),
    ("composed_key", "tenant-0001|2026-09-01"),
    ("non_ascii", "\u00f6tterworks"),
    ("raw_limit_2000", "x" * 2000),
    ("raw_limit_2001", "x" * 2001),
    ("raw_limit_multibyte_1500", "\u00f6" * 1500),
    ("long_4000", "x" * 4000),
    ("null", None),
]

CODE_DESC_MISS_INPUTS = [
    ("miss_val", "INV_STATUS", 99),
    ("miss_type", "NO_SUCH_TYPE", 1),
    ("null_val", "INV_STATUS", None),
    ("null_type", None, 10),
    ("negative_val", "INV_STATUS", -1),
    ("fractional_val", "INV_STATUS", 1.5),
    ("sub_one_val", "INV_STATUS", 0.5),
    ("zero_val", "INV_STATUS", 0),
    ("trailing_zero_val", "INV_STATUS", 1.50),
    ("wide_val", "INV_STATUS", 999999999999),
    ("empty_type", "", 10),
]

DT2STR_INPUTS = [
    ("null", None),
    ("mid_2026", "2026-09-01 00:00:00"),
    ("last_1999", "1999-12-31 00:00:00"),
    ("y2k", "2000-01-01 00:00:00"),
    ("pre_1900", "1899-03-05 00:00:00"),
    ("y2099", "2099-07-04 00:00:00"),
    ("with_time", "2026-03-15 13:45:59"),
]

STR2DT_INPUTS = [
    ("canonical", "01-SEP-26"),
    ("unpadded_day", "1-SEP-26"),
    ("lowercase_month", "01-sep-26"),
    ("century_pivot_99", "31-DEC-99"),
    ("leap_day", "29-FEB-24"),
    ("impossible_day", "31-FEB-24"),
    ("not_a_date", "N/A"),
    ("empty", ""),
    ("null", None),
    ("full_month_name", "01-SEPTEMBER-26"),
    ("surrounding_spaces", " 01-SEP-26 "),
    ("four_digit_year", "01-SEP-2026"),
    ("four_digit_year_past", "01-SEP-1999"),
    ("zero_padded_year", "01-SEP-0026"),
    ("single_digit_year", "01-SEP-2"),
    ("missing_year", "01-SEP"),
    ("slash_separator", "01/SEP/26"),
    ("trailing_text", "01-SEP-26 12:00"),
    ("wrong_order", "SEP-01-26"),
    ("numeric_month", "1-9-26"),
    ("month_prefix_typo", "01-JANU-26"),
]


def _secret(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"secret '{name}' not found in environment; pass secrets by name only")
    return value


def _jsonable(value):
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    return value


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(f"wrote {path}")


# --------------------------------------------------------------------------- transcript


def _oracle_connect(dsn_secret: str):
    import oracledb

    user, password, dsn = _secret(dsn_secret).split("/", 2)
    return oracledb.connect(user=user, password=password, dsn=dsn)


def _call(conn, sql: str, binds: dict, sizes: dict) -> dict:
    """Run one read-only package call, recording the value or the Oracle error."""
    import oracledb

    cursor = conn.cursor()
    try:
        cursor.setinputsizes(**sizes)
        cursor.execute(sql, binds)
        (value,) = cursor.fetchone()
        return {"value": _jsonable(value)}
    except oracledb.DatabaseError as exc:
        (error,) = exc.args
        return {"error": {"code": error.code, "message": error.message.strip().splitlines()[0]}}
    finally:
        cursor.close()


def capture_transcript(dsn_secret: str, out: Path) -> int:
    import oracledb

    conn = _oracle_connect(dsn_secret)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT CODE_TYPE, CODE_VAL FROM CODES ORDER BY CODE_TYPE, CODE_VAL")
        code_pairs = [(row[0], int(row[1])) for row in cursor.fetchall()]
        cursor.close()

        ops = []
        for label, value in MD5_INPUTS:
            ops.append({
                "fn": "f_md5_uuid",
                "label": label,
                "args": {"p_input": value},
                **_call(
                    conn,
                    "SELECT pkg_ow_util.f_md5_uuid(:p_input) FROM dual",
                    {"p_input": value},
                    {"p_input": oracledb.DB_TYPE_VARCHAR},
                ),
            })
        hit_inputs = [(f"hit_{code_type}_{code_val}", code_type, code_val)
                      for code_type, code_val in code_pairs]
        for label, code_type, code_val in hit_inputs + CODE_DESC_MISS_INPUTS:
            ops.append({
                "fn": "f_code_desc",
                "label": label,
                "args": {"p_type": code_type, "p_val": code_val},
                **_call(
                    conn,
                    "SELECT pkg_ow_util.f_code_desc(:p_type, :p_val) FROM dual",
                    {"p_type": code_type, "p_val": code_val},
                    {"p_type": oracledb.DB_TYPE_VARCHAR, "p_val": oracledb.DB_TYPE_NUMBER},
                ),
            })
        for label, text in DT2STR_INPUTS:
            value = (
                datetime.strptime(text, "%Y-%m-%d %H:%M:%S") if text is not None else None
            )
            ops.append({
                "fn": "f_dt2str",
                "label": label,
                "args": {"p_dt": _jsonable(value)},
                **_call(
                    conn,
                    "SELECT pkg_ow_util.f_dt2str(:p_dt) FROM dual",
                    {"p_dt": value},
                    {"p_dt": oracledb.DB_TYPE_DATE},
                ),
            })
        for label, text in STR2DT_INPUTS:
            ops.append({
                "fn": "f_str2dt",
                "label": label,
                "args": {"p_str": text},
                **_call(
                    conn,
                    "SELECT pkg_ow_util.f_str2dt(:p_str) FROM dual",
                    {"p_str": text},
                    {"p_str": oracledb.DB_TYPE_VARCHAR},
                ),
            })
    finally:
        conn.close()

    _write(out, {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "unit": "U7",
        "source": {
            "dsn_secret": dsn_secret,
            "package": "PKG_OW_UTIL",
            "access": "read-only; log_msg is never called (it inserts)",
        },
        "code_pairs": len(code_pairs),
        "ops": ops,
    })
    return 0


# ------------------------------------------------------------------------------- replay


def _load_port():
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    import ow_util

    return ow_util


def _port_result(fn, *args) -> dict:
    try:
        return {"value": _jsonable(fn(*args))}
    except Exception as exc:  # an Oracle-side error must show up as an error here too
        return {"raised": f"{type(exc).__name__}: {exc}"}


def _matches(expected: dict, actual: dict) -> bool:
    if "error" in expected:
        return "raised" in actual
    return "value" in actual and expected["value"] == actual["value"]


def replay_transcript(transcript: Path, uri_secret: str, out: Path) -> int:
    from pymongo import MongoClient

    ow_util = _load_port()
    recorded = json.loads(transcript.read_text())
    client = MongoClient(_secret(uri_secret))
    try:
        db = client[TARGET_DB]
        results = []
        for op in recorded["ops"]:
            args = op["args"]
            if op["fn"] == "f_md5_uuid":
                actual = _port_result(ow_util.md5_uuid, args["p_input"])
            elif op["fn"] == "f_code_desc":
                actual = _port_result(ow_util.code_desc, db, args["p_type"], args["p_val"])
            elif op["fn"] == "f_dt2str":
                raw = args["p_dt"]
                value = datetime.fromisoformat(raw["__datetime__"]) if raw else None
                actual = _port_result(ow_util.dt2str, value)
            elif op["fn"] == "f_str2dt":
                actual = _port_result(ow_util.str2dt, args["p_str"])
            else:
                raise RuntimeError(f"unknown transcript function {op['fn']}")
            expected = {k: v for k, v in op.items() if k in ("value", "error")}
            results.append({
                "fn": op["fn"],
                "label": op["label"],
                "args": args,
                "oracle": expected,
                "port": actual,
                "match": _matches(expected, actual),
            })
    finally:
        client.close()

    mismatches = [r for r in results if not r["match"]]
    by_fn = {}
    for r in results:
        counts = by_fn.setdefault(r["fn"], {"checks": 0, "matched": 0})
        counts["checks"] += 1
        counts["matched"] += int(r["match"])
    _write(out, {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "unit": "U7",
        "transcript": str(transcript.relative_to(REPO_ROOT)),
        "target_db": TARGET_DB,
        "secret_names": {"uri": uri_secret},
        "by_function": by_fn,
        "checks": len(results),
        "matched": len(results) - len(mismatches),
        "pass": not mismatches,
        "mismatches": mismatches[:20],
        "results": results,
    })
    print(f"replay: {len(results) - len(mismatches)}/{len(results)} matched")
    return 0 if not mismatches else 1


# ------------------------------------------------------------------------------- probes


def _ttl_index(collection) -> dict | None:
    for index in collection.list_indexes():
        if index["key"] == {"logged_at": 1}:
            return {
                "name": index["name"],
                "key": dict(index["key"]),
                "expireAfterSeconds": index.get("expireAfterSeconds"),
            }
    return None


def _probe_ttl_index(collection) -> dict:
    index = _ttl_index(collection)
    return {
        "index": index,
        "expected_expire_after_seconds": TTL_SECONDS,
        "pass": bool(index) and index["expireAfterSeconds"] == TTL_SECONDS,
    }


def _probe_ttl_expiry(collection, wait_seconds: int, poll_seconds: int) -> dict:
    probe_id = "u7-ttl-probe"
    aged_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=91)
    collection.delete_one({"_id": probe_id})
    collection.insert_one({
        "_id": probe_id,
        "logged_at": aged_at,
        "module": PROBE_MODULE,
        "message": "TTL expiry probe: logged_at is 91 days old",
        "ns": NS_VALUE,
    })
    started = time.monotonic()
    removed = False
    while time.monotonic() - started < wait_seconds:
        if collection.count_documents({"_id": probe_id}) == 0:
            removed = True
            break
        time.sleep(poll_seconds)
    elapsed = round(time.monotonic() - started, 1)
    collection.delete_one({"_id": probe_id})
    return {
        "inserted_logged_at": aged_at.isoformat(),
        "age_days": 91,
        "waited_seconds": elapsed,
        "wait_budget_seconds": wait_seconds,
        "removed_by_ttl": removed,
        # Not a gate: an unobserved sweep leaves TTL expiry declared-unexercised, it never
        # reports as observed.
        "observed": removed,
    }


def _probe_independence(client, collection, ow_util) -> dict:
    caller_id = "u7-caller-write"
    util = ow_util.OwUtil(client[TARGET_DB])
    collection.delete_many({"_id": caller_id})
    collection.delete_many({"module": PROBE_MODULE, "message": "autonomous audit write"})
    aborted = False
    with client.start_session() as session:
        session.start_transaction()
        collection.insert_one(
            {
                "_id": caller_id,
                "logged_at": datetime.now(timezone.utc).replace(microsecond=0),
                "module": PROBE_MODULE,
                "message": "caller transaction write",
                "ns": NS_VALUE,
            },
            session=session,
        )
        written = util.log_msg(PROBE_MODULE, "autonomous audit write")
        session.abort_transaction()
        aborted = True
    caller_survived = collection.count_documents({"_id": caller_id}) == 1
    audit_docs = list(collection.find({"module": PROBE_MODULE, "message": "autonomous audit write"}))
    collection.delete_many({"_id": caller_id})
    collection.delete_many({"module": PROBE_MODULE, "message": "autonomous audit write"})
    return {
        "caller_transaction_aborted": aborted,
        "log_msg_returned": written,
        "caller_write_rolled_back": not caller_survived,
        "audit_write_survived": len(audit_docs) == 1,
        "audit_write_concern": str(util.audit_collection.write_concern.document),
        "audit_write_used_session": False,
        "pass": aborted and written and not caller_survived and len(audit_docs) == 1,
    }


def _probe_truncation(client, collection, ow_util) -> dict:
    from bson import ObjectId

    util = ow_util.OwUtil(client[TARGET_DB])
    module = "M" * 40
    message = "m" * 5000
    before = datetime.now(timezone.utc).replace(microsecond=0)
    written = util.log_msg(module, message)
    doc = collection.find_one({"module": module[:30]})
    collection.delete_many({"module": module[:30]})
    return {
        "log_msg_returned": written,
        "module_source_length": len(module),
        "module_stored_length": len(doc["module"]) if doc else None,
        "message_source_length": len(message),
        "message_stored_length": len(doc["message"]) if doc else None,
        "id_is_object_id": bool(doc) and isinstance(doc["_id"], ObjectId),
        "ns": doc.get("ns") if doc else None,
        "logged_at_whole_seconds": bool(doc) and doc["logged_at"].microsecond == 0,
        "logged_at_not_before_call": bool(doc) and doc["logged_at"].replace(
            tzinfo=timezone.utc) >= before,
        "last_module_recorded": util.last_module == module,
        "pass": bool(doc)
        and written
        and len(doc["module"]) == 30
        and len(doc["message"]) == 4000
        and isinstance(doc["_id"], ObjectId)
        and doc.get("ns") == NS_VALUE
        and doc["logged_at"].microsecond == 0
        and util.last_module == module,
    }


def _probe_silent_failure(ow_util) -> dict:
    """A logging failure must return False and never reach the caller."""
    from pymongo import MongoClient

    unreachable = MongoClient(
        "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=200&connectTimeoutMS=200"
    )
    try:
        util = ow_util.OwUtil(unreachable[TARGET_DB])
        try:
            returned = util.log_msg(PROBE_MODULE, "unreachable target")
            raised = None
        except Exception as exc:
            returned = None
            raised = f"{type(exc).__name__}: {exc}"
    finally:
        unreachable.close()
    return {
        "log_msg_returned": returned,
        "raised": raised,
        "last_module_recorded": util.last_module == PROBE_MODULE,
        "pass": returned is False and raised is None and util.last_module == PROBE_MODULE,
    }


def run_probes(uri_secret: str, out: Path, wait_seconds: int, poll_seconds: int) -> int:
    from pymongo import MongoClient

    ow_util = _load_port()
    client = MongoClient(_secret(uri_secret))
    try:
        collection = client[TARGET_DB][AUDIT_COLLECTION]
        probes = {
            "ttl_index": _probe_ttl_index(collection),
            "ttl_expiry": _probe_ttl_expiry(collection, wait_seconds, poll_seconds),
            "autonomous_independence": _probe_independence(client, collection, ow_util),
            "truncation": _probe_truncation(client, collection, ow_util),
            "silent_failure": _probe_silent_failure(ow_util),
        }
        residual = collection.count_documents({"module": PROBE_MODULE})
    finally:
        client.close()

    gated = ["ttl_index", "autonomous_independence", "truncation", "silent_failure"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "unit": "U7",
        "namespace": NS_VALUE,
        "target_db": TARGET_DB,
        "collection": AUDIT_COLLECTION,
        "secret_names": {"uri": uri_secret},
        "probes": probes,
        "residual_probe_documents": residual,
        "gated_probes": gated,
        "pass": all(probes[name]["pass"] for name in gated) and residual == 0,
    }
    _write(out, payload)
    print(f"probes: pass={payload['pass']} ttl_expiry_observed={probes['ttl_expiry']['observed']}")
    return 0 if payload["pass"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("transcript", "replay", "probes"))
    parser.add_argument("--dsn-secret", default="OW_BILLING_FIXTURE_DSN")
    parser.add_argument("--uri-secret", default="MONGODB_ATLAS_URI")
    parser.add_argument("--transcript", type=Path, default=OUT_DIR / "util_transcript.json")
    parser.add_argument("--replay-out", type=Path, default=OUT_DIR / "util_parity.json")
    parser.add_argument("--probes-out", type=Path, default=OUT_DIR / "supplemental.json")
    parser.add_argument("--ttl-wait-seconds", type=int, default=240)
    parser.add_argument("--ttl-poll-seconds", type=int, default=5)
    args = parser.parse_args()

    if args.stage == "transcript":
        return capture_transcript(args.dsn_secret, args.transcript)
    if args.stage == "replay":
        return replay_transcript(args.transcript, args.uri_secret, args.replay_out)
    return run_probes(
        args.uri_secret, args.probes_out, args.ttl_wait_seconds, args.ttl_poll_seconds
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
