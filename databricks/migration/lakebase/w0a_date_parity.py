#!/usr/bin/env python3
"""Wave 0: prove billing.f_str2dt / f_dt2str match Oracle on the dirty-date anomaly set.

Oracle side is a read-only SELECT over dual using the package body's own expressions
(TO_DATE(x,'DD-MON-YY') with NLS_DATE_LANGUAGE=ENGLISH, NULL when it raises; TO_CHAR the
same way). Lakebase side calls the converted functions. Vectors cover the shapes the
anomaly set contains and the ones Postgres normalises where Oracle raises: impossible day,
impossible month/day pair, leap day in a non-leap year, padded and unpadded days, lower
case, stray whitespace, junk.

DEGRADED / official_verdict false: D10-01 denied, so this is a JDBC comparison, not the
harness's Oracle verdict.
"""
import json
import os
import sys

import oracledb
import psycopg

PARSE_VECTORS = [
    "01-JAN-24", "1-JAN-24", "15-MAR-99", "29-FEB-24", "29-FEB-23", "31-FEB-24",
    "32-JAN-24", "00-JAN-24", "31-APR-24", "15-mar-99", " 15-MAR-99 ", "15-XXX-99",
    "2024-03-15", "", "not a date", "15/MAR/99", "15-MAR-1999",
]
FORMAT_VECTORS = ["2024-01-03", "2024-12-31", "1999-03-15", "2024-02-29"]


def oracle_conn():
    parts = json.loads(os.environ["OW_TP_ORACLE_RO"])
    return oracledb.connect(
        user=parts["user"], password=parts["password"],
        dsn=f"{parts['host']}:{parts['port']}/{parts['service']}")


def main() -> int:
    report = {"grade": "DEGRADED", "official_verdict": False, "reason": "d10_01_denied",
              "parse": {}, "format": {}}
    failures = 0
    with oracle_conn() as ora, psycopg.connect(
            os.environ["OW_TP_LAKEBASE_DSN"]) as pg:
        with ora.cursor() as ocur, pg.cursor() as pcur:
            for value in PARSE_VECTORS:
                ocur.execute(
                    "SELECT TO_CHAR(TO_DATE(:1 DEFAULT NULL ON CONVERSION ERROR, "
                    "'DD-MON-YY', 'NLS_DATE_LANGUAGE=ENGLISH'), 'YYYY-MM-DD') FROM dual",
                    [value])
                want = ocur.fetchone()[0]
                pcur.execute("SELECT to_char(billing.f_str2dt(%s), 'YYYY-MM-DD')", (value,))
                got = pcur.fetchone()[0]
                report["parse"][value] = {"oracle": want, "lakebase": got,
                                          "match": want == got}
                failures += want != got

            for iso in FORMAT_VECTORS:
                ocur.execute(
                    "SELECT TO_CHAR(TO_DATE(:1,'YYYY-MM-DD'),'DD-MON-YY', "
                    "'NLS_DATE_LANGUAGE=ENGLISH') FROM dual", [iso])
                want = ocur.fetchone()[0]
                pcur.execute("SELECT billing.f_dt2str(%s::date)", (iso,))
                got = pcur.fetchone()[0]
                report["format"][iso] = {"oracle": want, "lakebase": got,
                                         "match": want == got}
                failures += want != got

    report["mismatches"] = failures
    print(json.dumps(report, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
