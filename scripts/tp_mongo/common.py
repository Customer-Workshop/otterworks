"""Shared plumbing for the Oracle -> MongoDB Atlas migration units.

Connections are named, never inlined: every entry point takes the NAME of an environment
variable and reads the value from the environment, so no credential reaches a source file,
a log line, or a PR body. The Oracle side is opened read-only by convention — these units
issue SELECT statements only.
"""

from __future__ import annotations

import hashlib
import os


def secret(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"secret '{name}' is not set in the environment; secrets are passed by name only")
    return value


def ns_batch_no(ns: str) -> int:
    """Deterministic conversion batch number for a namespace.

    Mirrors `services/legacy-billing/app/reports.py:ns_batch_no`, which is how the estate
    itself scopes every namespace's slice of the billing tables.
    """
    seed = int(hashlib.sha256(ns.encode()).hexdigest()[:8], 16)
    return seed % 90_000_000 + 1_000_000


def oracle_connect(dsn_secret: str):
    """Connect to the legacy estate. The secret holds `user/password/dsn`."""
    import oracledb

    user, password, dsn = secret(dsn_secret).split("/", 2)
    return oracledb.connect(user=user, password=password, dsn=dsn)


def mongo_database(uri_secret: str, database: str):
    from pymongo import MongoClient

    return MongoClient(secret(uri_secret))[database]
