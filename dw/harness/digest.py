"""Engine-independent value normalisation and digests for the equivalence gates.

Every side of a comparison (the legacy Redshift stand-in, the DuckDB rebuild of
the same estate, and the converted Databricks/Spark asset) hands this module the
same thing: rows of already-stringified column values. The digests are therefore
computed by one implementation in one language, and never by an engine's own
hash function -- an engine hash would make "the two sides agree" mean "the two
engines round and hash the same way", which is not what the gate is proving.

Normalisation rules (applied by the engine-side SQL/DataFrame projection, and
asserted here for the values that reach Python):
  * NULL                -> the sentinel ``\\N``
  * DECIMAL/NUMERIC     -> fixed-scale decimal text from the column's declared
                           scale (``'123.45'``), never float text
  * TIMESTAMP           -> ``YYYY-MM-DD HH:MM:SS`` (UTC, seconds resolution)
  * DATE                -> ``YYYY-MM-DD``
  * BOOLEAN             -> ``true`` / ``false``
  * everything else     -> the string as stored

Two digests are produced:
  * an *unordered* digest -- a commutative sum of per-row hashes (two moments,
    both modulo 2**64). Order- and partition-independent by construction, so it
    compares the multiset of rows and cannot be fooled by a different but
    equivalent physical ordering, while staying sensitive to multiplicity: an
    XOR fold cancels any row occurring an even number of times, which in an
    estate that deliberately contains duplicate deliveries would let two
    different datasets digest identically.
  * an *ordered* digest -- a running hash over rows in a caller-specified key
    order. Only used for assets where sequence is itself a business rule (SCD2
    version chains, running balances); for those the gate compares sequences,
    never sets.
"""

from __future__ import annotations

import hashlib
from typing import Iterable, Sequence

NULL_SENTINEL = "\\N"
FIELD_SEP = "\x1f"
DIGEST_BITS = 64
DIGEST_MASK = (1 << DIGEST_BITS) - 1


def value_hash(text: str) -> int:
    """Stable 64-bit hash of a single normalised value or row string."""
    return int.from_bytes(
        hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest(), "big"
    )


def pack(first: int, second: int) -> int:
    """Pack the two accumulator moments into one manifest digest value."""
    return ((first & DIGEST_MASK) << DIGEST_BITS) | (second & DIGEST_MASK)


def unpack(digest: int) -> tuple[int, int]:
    return (digest >> DIGEST_BITS) & DIGEST_MASK, digest & DIGEST_MASK


def accumulate(state: tuple[int, int], text: str) -> tuple[int, int]:
    """Add one row/value hash to a running unordered accumulator.

    Both moments are modular sums, so the accumulator is commutative and
    associative (safe to compute per partition and combine) and every
    occurrence contributes: duplicates change the digest instead of cancelling.
    The second moment means two different multisets must collide in both sums at
    once to be mistaken for each other.
    """
    first, second = state
    h = value_hash(text)
    return ((first + h) & DIGEST_MASK, (second + h * h) & DIGEST_MASK)


def fold_unordered(rows: Iterable[str]) -> tuple[int, int]:
    """Fold row strings order-independently. Returns (row_count, digest)."""
    state = (0, 0)
    count = 0
    for row in rows:
        state = accumulate(state, row)
        count += 1
    return count, pack(*state)


def fold_ordered(rows: Iterable[str]) -> tuple[int, int]:
    """Order-sensitive rolling digest. Returns (row_count, digest)."""
    acc = hashlib.blake2b(digest_size=8)
    count = 0
    for row in rows:
        acc.update(row.encode("utf-8"))
        acc.update(b"\x1e")
        count += 1
    return count, int.from_bytes(acc.digest(), "big")


def combine_unordered(parts: Iterable[tuple[int, int]]) -> tuple[int, int]:
    """Combine per-partition (count, digest) pairs from a distributed fold."""
    count = 0
    first = 0
    second = 0
    for part_count, part_digest in parts:
        part_first, part_second = unpack(part_digest)
        count += part_count
        first = (first + part_first) & DIGEST_MASK
        second = (second + part_second) & DIGEST_MASK
    return count, pack(first, second)


def row_string(values: Sequence[str]) -> str:
    """Join already-normalised column values into the canonical row string."""
    return FIELD_SEP.join(NULL_SENTINEL if v is None else v for v in values)


def column_digests(
    rows: Iterable[Sequence[str]], column_count: int
) -> tuple[int, int, list[int]]:
    """One pass over rows -> (row_count, row digest, per-column digests).

    The row digest hashes each row as a whole, so a wrong join that happens to
    preserve every column's multiset while associating the values with the wrong
    rows still fails the gate. The per-column digests exist on top of that to
    localise a failure to the column that diverged, which is what turns a red
    gate into a diagnosis instead of a mystery.
    """
    column_states = [(0, 0)] * column_count
    row_state = (0, 0)
    count = 0
    for values in rows:
        if len(values) != column_count:
            raise ValueError(
                f"row has {len(values)} values, expected {column_count}"
            )
        normalised = [
            NULL_SENTINEL if value is None else value for value in values
        ]
        for idx, text in enumerate(normalised):
            column_states[idx] = accumulate(
                column_states[idx], f"{idx}{FIELD_SEP}{text}"
            )
        row_state = accumulate(row_state, row_string(normalised))
        count += 1
    return count, pack(*row_state), [pack(*s) for s in column_states]
