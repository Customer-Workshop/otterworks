"""Translate the Redshift-only physical-layout clauses out of a DDL file."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


KNOWN_CODECS = {
    "az64",
    "bytedict",
    "delta32k",
    "lzo",
    "mostly8",
    "raw",
    "runlength",
    "text255",
    "text32k",
    "zstd",
}
KNOWN_DISTSTYLES = {"ALL", "AUTO", "EVEN", "KEY"}

ENCODE = re.compile(r"\s+ENCODE\s+([A-Za-z_][\w$]*)", re.IGNORECASE)
DISTSTYLE = re.compile(
    r"\s+DISTSTYLE\s+([A-Za-z_][\w$]*)", re.IGNORECASE
)
DISTKEY = re.compile(r"\s+DISTKEY\s*\([^)]*\)", re.IGNORECASE)
SORTKEY = re.compile(
    r"\s+(?:(?:COMPOUND|INTERLEAVED)\s+)?SORTKEY\s*\([^)]*\)",
    re.IGNORECASE,
)

# These tokens are Redshift-specific, but are not part of this translator's
# deliberately small supported surface. They are checked rather than dropped.
UNSUPPORTED = {
    "BACKUP": re.compile(r"\bBACKUP\b", re.IGNORECASE),
    "COMPUPDATE": re.compile(r"\bCOMPUPDATE\b", re.IGNORECASE),
    "IDENTITY": re.compile(r"\bIDENTITY\s*(?:\(|\b)", re.IGNORECASE),
    "MAXFILESIZE": re.compile(r"\bMAXFILESIZE\b", re.IGNORECASE),
    "STATUPDATE": re.compile(r"\bSTATUPDATE\b", re.IGNORECASE),
}


def _without_comments(sql: str) -> str:
    """Mask comments while preserving offsets for regex match locations."""
    chars = list(sql)
    index = 0
    while index < len(chars):
        if chars[index : index + 2] == ["-", "-"]:
            index += 2
            while index < len(chars) and chars[index] not in "\r\n":
                chars[index] = " "
                index += 1
            continue
        if chars[index : index + 2] == ["/", "*"]:
            chars[index] = " "
            chars[index + 1] = " "
            index += 2
            while index < len(chars):
                if chars[index : index + 2] == ["*", "/"]:
                    chars[index] = " "
                    chars[index + 1] = " "
                    index += 2
                    break
                if chars[index] not in "\r\n":
                    chars[index] = " "
                index += 1
            continue
        index += 1
    return "".join(chars)


def _validate(sql: str, source: Path) -> None:
    masked = _without_comments(sql)
    errors: list[str] = []

    for match in ENCODE.finditer(masked):
        codec = match.group(1).upper()
        if codec.lower() not in KNOWN_CODECS:
            errors.append(f"unknown ENCODE codec {match.group(1)!r}")

    for match in DISTSTYLE.finditer(masked):
        style = match.group(1).upper()
        if style not in KNOWN_DISTSTYLES:
            errors.append(f"unknown DISTSTYLE value {match.group(1)!r}")

    for name, pattern in UNSUPPORTED.items():
        if pattern.search(masked):
            errors.append(f"unsupported Redshift construct {name}")

    if errors:
        details = "; ".join(dict.fromkeys(errors))
        raise ValueError(f"{source}: {details}")


def translate(sql: str, source: Path = Path("<input>")) -> tuple[str, dict[str, int]]:
    """Return translated SQL and counts of the supported clauses removed."""
    _validate(sql, source)
    masked = _without_comments(sql)
    matches = [
        ("ENCODE", match)
        for match in ENCODE.finditer(masked)
    ]
    matches.extend(
        ("DISTSTYLE", match) for match in DISTSTYLE.finditer(masked)
    )
    matches.extend(("DISTKEY", match) for match in DISTKEY.finditer(masked))
    matches.extend(("SORTKEY", match) for match in SORTKEY.finditer(masked))

    output: list[str] = []
    cursor = 0
    counts = {"ENCODE": 0, "DISTSTYLE": 0, "DISTKEY": 0, "SORTKEY": 0}
    for clause, match in sorted(matches, key=lambda item: item[1].start()):
        output.append(sql[cursor : match.start()])
        cursor = match.end()
        counts[clause] += 1
    output.append(sql[cursor:])
    return "".join(output), counts


def _inputs(paths: list[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in paths:
        if path.is_dir():
            expanded.extend(sorted(path.glob("*.sql")))
        else:
            expanded.append(path)
    if not expanded:
        raise ValueError("no SQL input files found")
    return expanded


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="write translated files here, retaining each input basename",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate supported Redshift clauses without writing output",
    )
    args = parser.parse_args()

    paths = _inputs(args.inputs)
    if args.out_dir is not None:
        args.out_dir.mkdir(parents=True, exist_ok=True)
    elif len(paths) > 1 and not args.check:
        parser.error("multiple inputs require --out-dir")

    for path in paths:
        translated, counts = translate(path.read_text(), path)
        summary = ", ".join(
            f"{name}={count}" for name, count in counts.items() if count
        ) or "none"
        print(f"{path.name}: stripped {summary}", file=sys.stderr)
        if args.check:
            continue
        if args.out_dir is None:
            sys.stdout.write(translated)
        else:
            (args.out_dir / path.name).write_text(translated)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        print(error, file=sys.stderr)
        raise SystemExit(2)
