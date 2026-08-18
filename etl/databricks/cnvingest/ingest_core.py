"""Transport core for the sftp_ingest_poll conversion (namespace slice cnvingest).

Byte-transparent replacement for etl/legacy-extra/jobs/sftp_ingest_poll.ksh.
Pure Python, no Spark imports: the Databricks notebook wires it to Delta via
a Bronze adapter, and the fixture recon wires it to a local JSON registry.

Contract: docs/tech-partnerships/contracts/sftp_ingest_poll-cnvingest.contract.json
- transport only, never inspects file contents beyond counting lines
- raw lines decoded as latin-1 (lossless 1:1 byte-to-codepoint mapping)
- atomic visibility: hidden staging path + rename-into-place, no size-settle
- drop file deleted only after stage + archive + bronze registration succeed
- deterministic ids via uuid5, archive names carry sha256[:16], no timestamps
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import uuid
from dataclasses import dataclass

NS_RE = re.compile(r"[a-z0-9_]{1,24}")
GLOB = "CUSTBILL*.dat"
STAGING_PREFIX = ".staging."


def require_ns(ns: str) -> str:
    if not NS_RE.fullmatch(ns):
        raise ValueError(f"ns must match [a-z0-9_]{{1,24}}: {ns!r}")
    return ns


@dataclass
class StagedFile:
    file_name: str
    sha256: str
    bytes: int
    lines: int
    ingest_id: str


def deterministic_ingest_id(ns: str, file_name: str, sha256: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ow_tp/{ns}/sftp_ingest_poll/{file_name}/{sha256}"))


def split_raw_lines(data: bytes) -> list[str]:
    """Byte-level newline-only line split, decoded latin-1 verbatim.

    str.splitlines() would also break on VT/FF/FS/GS/RS/NEL, which are
    ordinary data bytes in an opaque mainframe extract; splitting the raw
    bytes on \n alone keeps line boundaries byte-transparent (any \r stays
    in the line verbatim). A trailing newline yields no empty final line.
    """
    if not data:
        return []
    chunks = data.split(b"\n")
    if chunks[-1] == b"":
        chunks.pop()
    return [chunk.decode("latin-1") for chunk in chunks]


def discover(drop_dir: str) -> list[str]:
    """Names in the drop dir matching the legacy glob CUSTBILL*.dat.

    Anything else (*.filepart in-flight transfers, unrelated names) is left
    untouched, matching the legacy glob exactly.
    """
    if not os.path.isdir(drop_dir):
        return []
    return sorted(
        name
        for name in os.listdir(drop_dir)
        if fnmatch.fnmatchcase(name, GLOB)
        and not name.startswith(STAGING_PREFIX)
        and os.path.isfile(os.path.join(drop_dir, name))
    )


def _write_atomic(directory: str, name: str, data: bytes) -> str:
    """Write via a hidden staging path, then rename into place.

    The file is never readable at its final path until complete; retires the
    legacy 1s size-settle heuristic.
    """
    final = os.path.join(directory, name)
    staging = os.path.join(directory, f"{STAGING_PREFIX}{name}")
    with open(staging, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(staging, final)
    with open(final, "rb") as fh:
        written = fh.read()
    if written != data:
        raise IOError(f"post-rename verification failed for {final}")
    return final


def ingest_batch(root: str, ns: str, bronze) -> list[StagedFile]:
    """One per-batch poll of <root>/drop.

    bronze must expose register(staged: StagedFile, raw_lines: list[str]) and
    raise on failure. On any failure the drop file is left in place and the
    exception propagates (no suppression).
    """
    require_ns(ns)
    drop_dir = os.path.join(root, "drop")
    incoming_dir = os.path.join(root, "incoming")
    archive_dir = os.path.join(root, "archive")
    os.makedirs(incoming_dir, exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)
    staged: list[StagedFile] = []
    for name in discover(drop_dir):
        src = os.path.join(drop_dir, name)
        with open(src, "rb") as fh:
            data = fh.read()
        digest = hashlib.sha256(data).hexdigest()
        raw_lines = split_raw_lines(data)
        record = StagedFile(
            file_name=name,
            sha256=digest,
            bytes=len(data),
            lines=len(raw_lines),
            ingest_id=deterministic_ingest_id(ns, name, digest),
        )
        _write_atomic(incoming_dir, name, data)
        _write_atomic(archive_dir, f"{name}.{digest[:16]}", data)
        bronze.register(record, raw_lines)
        os.remove(src)
        staged.append(record)
    return staged
