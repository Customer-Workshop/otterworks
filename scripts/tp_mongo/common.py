"""Shared plumbing for the Oracle -> MongoDB Atlas migration units.

Connections are named, never inlined: every entry point takes the NAME of an environment
variable and reads the value from the environment, so no credential reaches a source file,
a log line, or a PR body. The Oracle side is opened read-only by convention — these units
issue SELECT statements only.
"""

from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import json
import os
import re
from pathlib import Path

from bson.decimal128 import Decimal128

MAPPING_SPEC = Path(".migration/03_mapping_spec.json")
CONVENTIONS = Path(".migration/01_conventions.md")

# The cluster credential can write any database on the cluster, several of which belong to
# other owners, so the designated pair is read from the conventions record and enforced by
# every unit rather than trusted from the command line.
DB_ROWS = {"target_db": "Database", "quarantine_db": "Quarantine database"}
CLUSTER_ROW = re.compile(r"^\|\s*Cluster\s*\|[^|]*`([A-Za-z0-9.-]+\.mongodb\.net)`", re.MULTILINE)
URI_SECRET_ROW = re.compile(r"^\|\s*Target cluster URI\s*\|\s*`([A-Z0-9_]+)`", re.MULTILINE)

# The SRV host of a connection string: everything between the credentials and the path. Only
# the `mongodb+srv://` form is accepted, because a standard seed list names generated shard
# hosts (`ac-...-shard-00-00.<subdomain>.mongodb.net`) that do not identify their cluster.
URI_SRV_HOST = re.compile(r"^mongodb\+srv://(?:[^@/]*@)?([^/?]+)(?:[/?]|$)")

# A namespace is part of every `_id` a loader mints and of the filter its deletes run on, so
# it is checked before it can reach either.
NS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}


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


def designated_database(conventions_path: Path, row: str) -> str:
    """The database named on one row of the conventions record's target table."""
    pattern = re.compile(rf"^\|\s*{row}\s*\|\s*`([^`]+)`\s*\|", re.MULTILINE)
    match = pattern.search(conventions_path.read_text())
    if match is None:
        raise SystemExit(f"{conventions_path} declares no '{row}' row")
    return match.group(1)


def assert_designated(conventions_path: Path, **databases: str) -> None:
    for argument, given in databases.items():
        expected = designated_database(conventions_path, DB_ROWS[argument])
        if given != expected:
            raise SystemExit(
                f"--{argument.replace('_', '-')} {given!r} is not the database designated in "
                f"{conventions_path} ({expected!r}); writing anywhere else is out of bounds")


def designated_row(conventions_path: Path, pattern: re.Pattern[str], what: str) -> str:
    match = pattern.search(conventions_path.read_text())
    if match is None:
        raise SystemExit(f"{conventions_path} names no {what}")
    return match.group(1)


def assert_designated_cluster(conventions_path: Path, uri_secret: str) -> None:
    """The database names alone do not bound the target: the same two names exist on any
    cluster the operator can reach. The connection string must be the SRV URI of the cluster
    the conventions record designates, and it must arrive under the secret NAME recorded
    there.

    Only the host of the connection string is ever read, never echoed.
    """
    expected_secret = designated_row(conventions_path, URI_SECRET_ROW, "target cluster URI secret")
    if uri_secret != expected_secret:
        raise SystemExit(
            f"--target-uri-secret {uri_secret!r} is not the secret NAME designated in "
            f"{conventions_path} ({expected_secret!r})")

    expected_host = designated_row(conventions_path, CLUSTER_ROW, "target cluster host")
    host = URI_SRV_HOST.match(secret(uri_secret))
    if host is None:
        raise SystemExit(
            f"secret '{uri_secret}' does not hold a 'mongodb+srv://' connection string; a "
            f"standard seed list names generated shard hosts, which do not identify the "
            f"cluster they belong to")
    # The whole host section, not a prefix of it: a port or a second seed host appended to the
    # designated name would otherwise reach the client unexamined.
    if host.group(1).lower() != expected_host:
        raise SystemExit(
            f"secret '{uri_secret}' points at a cluster other than the designated "
            f"{expected_host}; writing anywhere else is out of bounds")


def assert_target(ns: str, conventions_path: Path, uri_secret: str, **databases: str) -> int:
    """Every boundary a unit can cross, checked before a client is constructed: the namespace
    it will stamp and delete by, the databases it will write, and the cluster they live on.
    Returns the namespace's conversion batch number."""
    if not NS_RE.match(ns):
        raise SystemExit(f"namespace {ns!r} is not of the form {NS_RE.pattern}")
    assert_designated(conventions_path, **databases)
    assert_designated_cluster(conventions_path, uri_secret)
    return ns_batch_no(ns)


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
        return dt.datetime(century + int(year), MONTHS[mon], int(day), tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def load_fields(spec_path: Path, unit: str) -> list[tuple[str, str, str, list[str]]]:
    """`(source column, target path, bson type, rules)` for a unit's collection, straight from
    the approved mapping spec — the loader and recon read the same rule list, so a field can
    never be canonicalized one way at load time and compared another way."""
    spec = json.loads(spec_path.read_text())
    collections = [c for c in spec["collections"] if c["collection"] == unit]
    if not collections:
        raise SystemExit(f"mapping spec {spec_path} has no '{unit}' collection")
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
