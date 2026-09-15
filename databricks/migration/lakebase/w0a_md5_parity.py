#!/usr/bin/env python3
"""D2-01: prove billing.f_md5_uuid on Lakebase is byte-identical to Oracle's
ow_billing.pkg_ow_util.f_md5_uuid, on the inputs the estate actually hashes.

One live Oracle read (inside the source query cap): Oracle hashes inputs taken from real
rows, Lakebase hashes the same inputs with billing.f_md5_uuid, and the two are compared
exactly.

UNVERIFIED PATH: the comparison uses the package body's own expression
(STANDARD_HASH(UTL_RAW.CAST_TO_RAW(x),'MD5') formatted 8-4-4-4-12) inline, not a call to
ow_billing.pkg_ow_util.f_md5_uuid. The read-only user has no EXECUTE on the package
(ORA-41900) and granting it would be DDL on a read-only source. So this proves the algorithm
is identical, not that the package entrypoint is reachable. Recorded as unverified rather
than worked around.

The script also checks whether stored ids equal the hash of their derivation input. They do
not for seeded rows - the fixture seed inserted literal ids rather than going through the
package - so converted code must CARRY ids across, never recompute them. That is reported,
not treated as a parity failure.

usage: run under with_oracle_secret.py and with_lakebase_dsn.py, e.g.
  python3 .../with_oracle_secret.py OW_TP_ORACLE_RO ow-tp/oracle/ow_billing_ro -- \
  python3 /home/ubuntu/with_lakebase_dsn.py mig-p1-w0 -- \
  python3 databricks/migration/lakebase/w0a_md5_parity.py
"""
import json
import os
import sys

import oracledb
import psycopg

# The package body's hash expression, inlined (see UNVERIFIED PATH above).
H = ("LOWER(RAWTOHEX(STANDARD_HASH(UTL_RAW.CAST_TO_RAW({x}), 'MD5')))")


def hashed(expr: str) -> str:
    """Oracle SQL returning the package's 8-4-4-4-12 form of MD5(expr)."""
    h = H.format(x=expr)
    return (f"SUBSTR({h},1,8)||'-'||SUBSTR({h},9,4)||'-'||SUBSTR({h},13,4)||'-'||"
            f"SUBSTR({h},17,4)||'-'||SUBSTR({h},21,12)")


PERIOD_KEY = "tenant_id || TO_CHAR(period_start, 'YYYY-MM-DD')"

# vector name -> (oracle sql yielding (input, oracle_hash, stored_id), derivation note)
VECTORS = {
    "rating_results": (
        f"SELECT period_id, {hashed('period_id')}, id "
        "FROM ow_billing.rating_results ORDER BY period_id",
        "f_md5_uuid(period_id)",
    ),
    "invoice_lines": (
        f"SELECT invoice_id || TO_CHAR(line_no), "
        f"{hashed('invoice_id || TO_CHAR(line_no)')}, id "
        "FROM ow_billing.invoice_lines ORDER BY 1",
        "f_md5_uuid(invoice_id || line_no)",
    ),
    "rating_periods": (
        f"SELECT {PERIOD_KEY}, {hashed(PERIOD_KEY)}, id "
        "FROM ow_billing.rating_periods ORDER BY 1",
        "f_md5_uuid(tenant_id || period_start)",
    ),
    "customer_master": (
        f"SELECT cust_id, {hashed('cust_id')}, NULL "
        "FROM ow_billing.customer_master ORDER BY cust_id FETCH FIRST 2000 ROWS ONLY",
        "f_md5_uuid(cust_id) - volume vector, 2000 real strings",
    ),
}
# Edge cases Oracle and Postgres can disagree on. Oracle VARCHAR2 treats '' as NULL, so the
# empty-string row is a known, declared divergence rather than a parity failure.
EDGE_CASES = ["", " ", "0", "NULL", "a" * 4000, "\u00e9\u00e7\u00fc"]


def oracle_conn():
    parts = json.loads(os.environ["OW_TP_ORACLE_RO"])
    return oracledb.connect(
        user=parts["user"], password=parts["password"],
        dsn=f"{parts['host']}:{parts['port']}/{parts['service']}")


def main() -> int:
    report = {"vectors": {}, "edge_cases": {}, "grade": "DEGRADED",
              "official_verdict": False, "reason": "d10_01_denied",
              "unverified_paths": [
                  "ow_billing.pkg_ow_util.f_md5_uuid not called directly: the read-only "
                  "user has no EXECUTE on the package (ORA-41900) and granting it would be "
                  "DDL on a read-only source. The package body's own hash expression is "
                  "used inline instead, so the algorithm is proven and the entrypoint is "
                  "not.",
              ]}
    failures = 0
    with oracle_conn() as ora, psycopg.connect(os.environ["OW_TP_LAKEBASE_DSN"]) as pg:
        for name, (sql, note) in VECTORS.items():
            with ora.cursor() as cur:
                rows = [(r[0], r[1], r[2]) for r in cur.execute(sql)]
            mismatched = []
            stored_id_derived = 0
            stored_ids_present = 0
            with pg.cursor() as cur:
                for value, oracle_hash, stored_id in rows:
                    cur.execute("SELECT billing.f_md5_uuid(%s)", (value,))
                    got = cur.fetchone()[0]
                    if got != oracle_hash:
                        mismatched.append({"input": value, "oracle": oracle_hash,
                                           "lakebase": got})
                    if stored_id is not None:
                        stored_ids_present += 1
                        if stored_id == oracle_hash:
                            stored_id_derived += 1
            report["vectors"][name] = {
                "expression": note, "rows": len(rows),
                "mismatches": len(mismatched), "examples": mismatched[:5],
                "stored_ids_checked": stored_ids_present,
                "stored_ids_matching_derivation": stored_id_derived,
            }
            failures += len(mismatched)

        # Edge cases: Oracle is asked directly via a SELECT over dual, which is a read.
        for value in EDGE_CASES:
            with ora.cursor() as cur:
                cur.execute(
                    "SELECT LOWER(RAWTOHEX(STANDARD_HASH(UTL_RAW.CAST_TO_RAW(:1), 'MD5'))) "
                    "FROM dual", [value])
                hexed = cur.fetchone()[0]
            expected = None if hexed is None else (
                f"{hexed[0:8]}-{hexed[8:12]}-{hexed[12:16]}-{hexed[16:20]}-{hexed[20:32]}")
            with pg.cursor() as cur:
                cur.execute("SELECT billing.f_md5_uuid(%s)", (value,))
                got = cur.fetchone()[0]
            key = repr(value)[:24]
            report["edge_cases"][key] = {"oracle": expected, "lakebase": got,
                                         "match": expected == got}
            if expected != got and value != "":
                failures += 1

    report["mismatches"] = failures
    report["verdict"] = "PARITY" if failures == 0 else "MISMATCH"
    out = ".migration/recon/U-01/md5_parity.json"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        json.dump(report, fh, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != "vectors"}, indent=2))
    print(json.dumps(report["vectors"], indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
