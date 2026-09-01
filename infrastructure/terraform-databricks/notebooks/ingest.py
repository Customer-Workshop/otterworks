# Databricks notebook source
"""`ingest` task of job ow_tp_custbill: conversion of etl/legacy-extra/jobs/sftp_ingest_poll.ksh.

Polls `/Volumes/ow_tp/bronze/landing/<ns>/incoming/` for CUSTBILL*.dat files, archives
each one under a content-addressed name, loads every line byte-transparently into
ow_tp.bronze.custbill_raw and only then removes the incoming copy. Contract:
docs/tech-partnerships/contracts/sftp_ingest_poll.contract.json.

The pure helpers above `main()` have no Spark or dbutils dependency so they can be
imported and unit-tested from scripts/tp_dbx/tests.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

CATALOG = "ow_tp"
BRONZE = f"{CATALOG}.bronze.custbill_raw"
LANDING = f"/Volumes/{CATALOG}/bronze/landing"
NS_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
BRONZE_COLUMNS = ("ns", "source_file", "line_no", "record_kind", "raw_line", "file_sha256")


def require_ns(ns: str) -> str:
    if not NS_RE.fullmatch(ns or ""):
        raise ValueError(f"ns must match [a-z0-9][a-z0-9-]{{0,31}}: {ns!r}")
    return ns


def is_eligible(name: str) -> bool:
    """CUSTBILL*.dat only; `.part`/`.tmp` are in-flight producer writes."""
    return name.startswith("CUSTBILL") and name.endswith(".dat")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def archive_name(basename: str, digest: str) -> str:
    return f"{basename}.{digest[:12]}"


def record_kind(line: bytes) -> str:
    if line.startswith(b"HDR"):
        return "HDR"
    if line.startswith(b"TRL"):
        return "TRL"
    return "BODY"


def split_lines(data: bytes) -> list[bytes]:
    """Split on b"\\n" only, dropping the empty element after a trailing newline.
    `\\r` and every other byte stay inside the line."""
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    return lines


def is_utf8(data: bytes) -> bool:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def bronze_rows(ns: str, source_file: str, data: bytes, digest: str) -> list[tuple]:
    """One row per line, `raw_line` decoded latin-1 so every byte survives a re-encode."""
    return [
        (ns, source_file, line_no, record_kind(line), line.decode("latin-1"), digest)
        for line_no, line in enumerate(split_lines(data), start=1)
    ]


def should_skip_as_duplicate(
    digest: str, known_digests: set[str], archive_exists: bool = False, rowless: bool = False
) -> bool:
    """Bronze digests are the marker for files that produced rows. A row-less (zero-byte)
    file leaves nothing in bronze, so its content-addressed archive entry is the durable
    marker instead; for non-empty files an archive entry alone never suppresses the load."""
    return digest in known_digests or (rowless and archive_exists)


RUN_LOG: list[str] = []


def log(**fields) -> None:
    line = " ".join(f"{key}={value}" for key, value in fields.items())
    RUN_LOG.append(line)
    print(line, flush=True)


def finish(summary: str) -> None:
    dbutils.notebook.exit(json.dumps({"summary": summary, "log": RUN_LOG}))  # noqa: F821


def main() -> None:
    from pyspark.sql import functions as F
    from pyspark.sql.types import IntegerType, StringType, StructField, StructType

    ns = require_ns(dbutils.widgets.get("ns"))  # noqa: F821 - injected by Databricks
    incoming_dir = f"{LANDING}/{ns}/incoming"
    archive_dir = f"{LANDING}/{ns}/archive"
    log(stage="ingest", ns=ns, incoming=incoming_dir)

    names = sorted(n for n in os.listdir(incoming_dir)) if os.path.isdir(incoming_dir) else []
    eligible = [n for n in names if is_eligible(n) and os.path.isfile(f"{incoming_dir}/{n}")]
    for name in names:
        if name not in eligible:
            log(file=name, action="skipped", reason="not CUSTBILL*.dat")
    if not eligible:
        log(action="no files", ns=ns, rows_inserted=0)
        finish("no files")
        return

    known = {
        row[0] for row in spark.sql(  # noqa: F821
            f"SELECT DISTINCT file_sha256 FROM {BRONZE} WHERE ns = :ns", args={"ns": ns}
        ).collect()
    }
    schema = StructType([
        StructField("ns", StringType(), False),
        StructField("source_file", StringType(), False),
        StructField("line_no", IntegerType(), False),
        StructField("record_kind", StringType(), False),
        StructField("raw_line", StringType(), False),
        StructField("file_sha256", StringType(), False),
    ])
    os.makedirs(archive_dir, exist_ok=True)
    total_inserted = 0

    for name in eligible:
        incoming_path = f"{incoming_dir}/{name}"
        with open(incoming_path, "rb") as handle:
            data = handle.read()
        digest = sha256_hex(data)
        log(file=name, action="read", bytes=len(data), sha256=digest)
        if len(data) == 0:
            log(file=name, action="empty", sha256=digest)
        if not is_utf8(data):
            log(file=name, action="non_utf8", sha256=digest, note="loaded via latin-1")

        archive_path = f"{archive_dir}/{archive_name(name, digest)}"
        already_archived = os.path.isfile(archive_path)
        with open(archive_path, "wb") as handle:
            handle.write(data)
        with open(archive_path, "rb") as handle:
            archived_digest = sha256_hex(handle.read())
        if archived_digest != digest:
            raise RuntimeError(f"archive verification failed for {name}: {archived_digest} != {digest}")
        log(file=name, action="archived", archive=archive_path, sha256_verified=True)

        if should_skip_as_duplicate(digest, known, already_archived, rowless=len(data) == 0):
            log(file=name, action="duplicate", sha256=digest, rows_inserted=0)
        else:
            rows = bronze_rows(ns, name, data, digest)
            spark.sql(  # noqa: F821
                f"DELETE FROM {BRONZE} WHERE ns = :ns AND source_file = :f AND file_sha256 = :d",
                args={"ns": ns, "f": name, "d": digest},
            )
            if rows:
                (
                    spark.createDataFrame(rows, schema)  # noqa: F821
                    .withColumn("ingested_at", F.current_timestamp())
                    .write.mode("append")
                    .saveAsTable(BRONZE)
                )
            known.add(digest)
            total_inserted += len(rows)
            log(file=name, action="landed", sha256=digest, rows_inserted=len(rows))

        os.remove(incoming_path)
        log(file=name, action="removed_incoming", path=incoming_path)

    log(action="done", ns=ns, files=len(eligible), rows_inserted=total_inserted)
    finish(f"files={len(eligible)} rows_inserted={total_inserted}")


if __name__ == "__main__":
    main()
