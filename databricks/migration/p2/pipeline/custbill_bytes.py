"""Byte-level CUSTBILL primitives, shared by the pipeline and by the fixture tests.

No pyspark import: this is the part of the conversion that has to be testable
against the captured legacy bytes without a cluster, and the part where a wrong
answer is invisible until recon.

Record contract clauses implemented here: C-1.3 (slicing is by byte offset, not
character), C-1.4 (ISO-8859-1 round-trips every byte), C-4.1 (HDR/TRL deletion
is a prefix test on the raw line, so a customer id starting with those letters
is deleted as if it were a header).
"""

from __future__ import annotations

ENCODING = "iso-8859-1"
HEADER_PREFIXES = (b"HDR", b"TRL")


def split_records(content: bytes) -> list[tuple[int, str, int]]:
    """Split landed file bytes into (record_no, raw_record, record_bytes).

    Split on LF only. A CR stays inside the record: the legacy parser keeps it
    too, so on a CRLF file it sits at byte 66 and falls off the end of the
    65-byte layout. Stripping it would change what the parser sees.

    A trailing LF closes the last record, so the empty piece after it is not a
    record. A blank line in the middle of a file *is* a record — the legacy
    emits an all-empty row for it.
    """
    if content is None:
        return []
    parts = bytes(content).split(b"\n")
    if parts and parts[-1] == b"":
        parts.pop()
    return [(i + 1, part.decode(ENCODING), len(part)) for i, part in enumerate(parts)]


def is_header_or_trailer(raw_record: str) -> bool:
    """True for a line the legacy `sed -e '/^HDR/d' -e '/^TRL/d'` deletes."""
    return raw_record.encode(ENCODING).startswith(HEADER_PREFIXES)


def data_records(content: bytes) -> list[tuple[int, str, int]]:
    """The records the legacy parser actually parses: everything sed did not delete."""
    return [rec for rec in split_records(content) if not is_header_or_trailer(rec[1])]
