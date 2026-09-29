#!/usr/bin/env python3
"""Render and run the Snowflake bootstrap scripts (SNOWFLAKE-PORT-SPEC.md §4).

    bootstrap.py --account                 # once per account, as ACCOUNTADMIN: LDM_ADMIN, LDM_WH, resource monitor
    bootstrap.py --tenant o29-after        # per demo token, as LDM_ADMIN: database + LDM_JOB_<TOKEN> role
    bootstrap.py --teardown o29-after      # drop the tenant database + role
    bootstrap.py --render --tenant o29-after   # print the SQL instead of running it (paste into a worksheet)

Connection comes from the environment only (never argv): SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PAT
(programmatic access token). The token's user needs ACCOUNTADMIN for --account and LDM_ADMIN afterwards.
Tokens are upper-cased with `-` -> `_` for identifiers: o29-after -> OTTERWORKS_LDM_O29_AFTER / LDM_JOB_O29_AFTER.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,62}$")


def sf_token(namespace: str) -> str:
    if not TOKEN_RE.match(namespace):
        raise SystemExit(f"invalid namespace token {namespace!r}")
    return namespace.upper().replace("-", "_")


def render(name: str, **vars: str) -> str:
    text = (HERE / name).read_text(encoding="utf-8")
    for k, v in vars.items():
        if not re.fullmatch(r"[A-Z0-9_]+", v):
            raise SystemExit(f"{k}={v!r} is not a plain identifier")
        text = text.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z_]+\}\}", text)
    if left:
        raise SystemExit(f"{name}: unbound placeholders {sorted(set(left))}")
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--account", action="store_true", help="account-level objects (ACCOUNTADMIN)")
    g.add_argument("--tenant", metavar="TOKEN", help="per-tenant database + job role (LDM_ADMIN)")
    g.add_argument("--teardown", metavar="TOKEN", help="drop the tenant database + job role (LDM_ADMIN)")
    ap.add_argument("--job-user", default=os.environ.get("SNOWFLAKE_JOB_USER") or os.environ.get("SNOWFLAKE_USER", ""))
    ap.add_argument("--credit-quota", type=int, default=int(os.environ.get("SNOWFLAKE_CREDIT_QUOTA", "20")))
    ap.add_argument("--render", action="store_true", help="print the SQL, do not connect")
    a = ap.parse_args(argv)

    user = os.environ.get("SNOWFLAKE_USER", "")
    if a.account:
        if not user:
            raise SystemExit("SNOWFLAKE_USER is required (the operator granted LDM_ADMIN)")
        sql = render("account.sql", ADMIN_USER=user.upper(), CREDIT_QUOTA=str(a.credit_quota))
        role = "ACCOUNTADMIN"
    elif a.tenant:
        if not a.job_user:
            raise SystemExit("--job-user / SNOWFLAKE_JOB_USER is required")
        sql = render("tenant.sql", TOKEN=sf_token(a.tenant), NAMESPACE=sf_token(a.tenant), JOB_USER=a.job_user.upper())
        role = "LDM_ADMIN"
    else:
        sql = render("teardown.sql", TOKEN=sf_token(a.teardown))
        role = "LDM_ADMIN"

    if a.render:
        sys.stdout.write(sql)
        return 0

    account, token = os.environ.get("SNOWFLAKE_ACCOUNT", ""), os.environ.get("SNOWFLAKE_PAT", "")
    if not (account and user and token):
        raise SystemExit("SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER and SNOWFLAKE_PAT must be set")
    import snowflake.connector

    conn = snowflake.connector.connect(
        account=account,
        user=user,
        authenticator="PROGRAMMATIC_ACCESS_TOKEN",
        token=token,
        role=role,
        autocommit=True,
        application="ldm-bootstrap",
        session_parameters={"QUERY_TAG": "ldm-bootstrap"},
    )
    try:
        for cur in conn.execute_string(sql, return_cursors=True):
            first = " ".join(cur.query.split())[:96]
            row = cur.fetchone() if cur.rowcount is None or cur.rowcount >= 0 else None
            print(f"ok  {first}" + (f"  -> {row[0]}" if row else ""))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
