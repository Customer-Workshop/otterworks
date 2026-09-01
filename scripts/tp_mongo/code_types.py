#!/usr/bin/env python3
"""Print the Oracle CODES enumeration for the U0 recon runner."""
from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn-secret", default="OW_BILLING_FIXTURE_DSN")
    args = parser.parse_args()
    if args.dsn_secret not in os.environ:
        raise RuntimeError(
            f"Oracle DSN secret environment variable name '{args.dsn_secret}' is not set"
        )
    try:
        user, password, dsn = os.environ[args.dsn_secret].split("/", 2)
    except ValueError as exc:
        raise RuntimeError(
            f"Oracle DSN secret '{args.dsn_secret}' must contain user/password/dsn"
        ) from exc
    if not user or not password or not dsn:
        raise RuntimeError(
            f"Oracle DSN secret '{args.dsn_secret}' must contain non-empty user/password/dsn"
        )

    # Evidence-backed expected values are recorded in schema/01_tables.sql (7)
    # and schema/02_horror.sql (3); coverage.md does not enumerate code_type values.
    import oracledb

    with oracledb.connect(user=user, password=password, dsn=dsn) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DISTINCT CODE_TYPE FROM CODES ORDER BY 1")
            for (code_type,) in cursor:
                print(code_type)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
