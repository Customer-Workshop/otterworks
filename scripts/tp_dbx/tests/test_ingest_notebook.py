"""Unit tests for the pure helpers of the `ingest` notebook (U6 sftp_ingest_poll).

The notebook is imported as a module; its `main()` (Spark/dbutils) is guarded by
`__name__ == "__main__"` and never runs here.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

NOTEBOOK = Path(__file__).resolve().parents[3] / "infrastructure/terraform-databricks/notebooks/ingest.py"


def _load():
    spec = importlib.util.spec_from_file_location("ingest_notebook", NOTEBOOK)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ingest = _load()


@pytest.mark.parametrize("line,kind", [
    (b"HDRCUSTBILL 2024", "HDR"),
    (b"TRL0000000050", "TRL"),
    (b"C000000001Acme", "BODY"),
    (b"", "BODY"),
    (b"hdr lowercase is body", "BODY"),
])
def test_record_kind_by_prefix(line: bytes, kind: str) -> None:
    assert ingest.record_kind(line) == kind


def test_archive_name_is_content_addressed() -> None:
    digest = hashlib.sha256(b"x").hexdigest()
    assert ingest.archive_name("CUSTBILL_A_001.dat", digest) == f"CUSTBILL_A_001.dat.{digest[:12]}"
    assert ingest.archive_name("CUSTBILL_A_001.dat", digest) == ingest.archive_name("CUSTBILL_A_001.dat", digest)


def test_split_lines_preserves_bytes_and_drops_only_trailing_newline() -> None:
    data = b"HDR header\r\ncaf\xe9\x0bbody\n\nTRL0\n"
    lines = ingest.split_lines(data)
    assert lines == [b"HDR header\r", b"caf\xe9\x0bbody", b"", b"TRL0"]
    assert ingest.split_lines(b"") == []
    assert ingest.split_lines(b"no newline") == [b"no newline"]


def test_bronze_rows_are_latin1_byte_transparent_and_one_based() -> None:
    data = b"HDR h\ncaf\xe9 \x0b  body   \nTRL0000000001\n"
    digest = ingest.sha256_hex(data)
    rows = ingest.bronze_rows("sftp-ingest-poll-w1", "CUSTBILL_X.dat", data, digest)
    assert [r[2] for r in rows] == [1, 2, 3]
    assert [r[3] for r in rows] == ["HDR", "BODY", "TRL"]
    assert rows[1][4] == "caf\xe9 \x0b  body   "
    rebuilt = b"".join(r[4].encode("latin-1") + b"\n" for r in rows)
    assert rebuilt == data
    assert all(r[0] == "sftp-ingest-poll-w1" and r[1] == "CUSTBILL_X.dat" and r[5] == digest for r in rows)
    assert len(rows[0]) == len(ingest.BRONZE_COLUMNS)


def test_bronze_rows_empty_file_yields_no_rows() -> None:
    assert ingest.bronze_rows("ns", "CUSTBILL_E.dat", b"", ingest.sha256_hex(b"")) == []


def test_is_utf8_flags_non_utf8_bytes() -> None:
    assert ingest.is_utf8(b"plain ascii\n")
    assert not ingest.is_utf8(b"caf\xe9\n")


@pytest.mark.parametrize("name,eligible", [
    ("CUSTBILL_DEMO_001.dat", True),
    ("CUSTBILL_DEMO_001.dat.part", False),
    ("CUSTBILL_DEMO_001.dat.tmp", False),
    ("CUSTBILL_DEMO_001.tmp", False),
    ("OTHER_001.dat", False),
    ("custbill_lower.dat", False),
])
def test_is_eligible(name: str, eligible: bool) -> None:
    assert ingest.is_eligible(name) is eligible


def test_duplicate_decision_uses_ns_known_digests() -> None:
    known = {"a" * 64}
    assert ingest.should_skip_as_duplicate("a" * 64, known)
    assert not ingest.should_skip_as_duplicate("b" * 64, known)
    assert not ingest.should_skip_as_duplicate("a" * 64, set())


def test_duplicate_decision_falls_back_to_archive_marker_for_rowless_files() -> None:
    empty_digest = ingest.sha256_hex(b"")
    assert ingest.bronze_rows("ns", "CUSTBILL_X.dat", b"", empty_digest) == []
    assert not ingest.should_skip_as_duplicate(empty_digest, set(), archive_exists=False, rowless=True)
    assert ingest.should_skip_as_duplicate(empty_digest, set(), archive_exists=True, rowless=True)


def test_archive_alone_never_suppresses_load_of_non_empty_file() -> None:
    digest = ingest.sha256_hex(b"HDR|x\n")
    assert not ingest.should_skip_as_duplicate(digest, set(), archive_exists=True, rowless=False)
    assert ingest.should_skip_as_duplicate(digest, {digest}, archive_exists=True, rowless=False)


@pytest.mark.parametrize("ns", ["demo", "sftp-ingest-poll-w1", "a" * 32])
def test_require_ns_accepts(ns: str) -> None:
    assert ingest.require_ns(ns) == ns


@pytest.mark.parametrize("ns", ["", "Demo", "-x", "a" * 33, "x;drop", "ns'--"])
def test_require_ns_rejects(ns: str) -> None:
    with pytest.raises(ValueError):
        ingest.require_ns(ns)
