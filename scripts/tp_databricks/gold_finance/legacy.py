"""The legacy side of the gold_finance recon: the real scripts, run, plus a model of the Perl.

Two independent things live here and they are deliberately not the same thing.

``parse()`` / ``report()`` execute the actual estate artifacts —
``etl/legacy-extra/jobs/parse_custbill_fixedwidth.sh`` and
``etl/legacy-extra/jobs/finance_excel_report.pl`` — through
``scripts/tp-run-deterministic.sh`` (TZ=UTC, LC_ALL=C, clock frozen by libfaketime so the report's
``localtime`` file stamp is reproducible). Their output CSV is the golden baseline the target is
compared against, byte for byte.

``model()`` re-expresses the Perl in Python: the ``next if ($cust eq "")`` skip, the ``"$ccy|$rt"``
key, ``$tot{$key} += $amt`` in IEEE-754 doubles (Python floats are the same doubles Perl uses, and
the accumulation order is the source's: files in ``sort`` order, lines in file order), ``sort keys
%tot`` as a byte-wise sort, and ``printf "%s,%s,%d,%.2f"``. It exists so ``ANOM-PERL-ROUNDING`` can
be quantified — the same population summed once in binary floating point and once in exact decimal,
differenced in cents — and so the executed script is compared against a second derivation of the
source's semantics rather than against itself.
"""

from __future__ import annotations

import decimal
import os
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[3]
DETERMINISTIC = ROOT / "scripts" / "tp-run-deterministic.sh"
PARSER = ROOT / "etl" / "legacy-extra" / "jobs" / "parse_custbill_fixedwidth.sh"
REPORT = ROOT / "etl" / "legacy-extra" / "jobs" / "finance_excel_report.pl"
# The clock the whole run is pinned to. The report stamps its file name with localtime, so a
# reproducible baseline needs a frozen clock, not just a frozen TZ.
FAKETIME = "2026-08-30 00:00:00"
CENT = decimal.Decimal("0.01")
LEADING_NUMBER = re.compile(r"^\s*[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


class LegacyError(RuntimeError):
    """A legacy artifact could not be executed. The brief says stop and report, not work around."""


def stamp(faketime: str = FAKETIME) -> str:
    """The `sprintf("%04d%02d%02d", ...)` stamp the report derives from `localtime`."""
    return faketime.split(" ")[0].replace("-", "")


def _run(argv: list[str], legacy_root: pathlib.Path, faketime: str) -> str:
    env = dict(os.environ)
    env["OTTERWORKS_LEGACY_ROOT"] = str(legacy_root)
    env["TP_FAKETIME"] = faketime
    proc = subprocess.run(
        [str(DETERMINISTIC), *argv],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise LegacyError(
            f"{' '.join(argv)} under OTTERWORKS_LEGACY_ROOT={legacy_root} exited "
            f"{proc.returncode}: {proc.stderr[-2000:]}"
        )
    return proc.stdout


def parse(legacy_root: pathlib.Path, faketime: str = FAKETIME) -> dict[str, int]:
    """Run the real parser over `<root>/incoming` and report the rows it wrote per file."""
    _run(["bash", str(PARSER)], legacy_root, faketime)
    return {
        path.name: len([line for line in path.read_text(encoding="latin-1").splitlines() if line])
        for path in sorted((legacy_root / "parsed").glob("CUSTBILL*.psv"))
    }


def stage(legacy_root: pathlib.Path, drops: dict[str, bytes]) -> None:
    """Write drop files into a private `<root>/incoming`, replacing whatever was there.

    The parser renames each input to `<file>.dat.done` as it consumes it, so a re-parse needs the
    inputs re-staged. Staging into a private root also keeps this unit out of any other unit's
    legacy working directory.
    """
    incoming = legacy_root / "incoming"
    for stale in incoming.glob("CUSTBILL*"):
        stale.unlink()
    for stale in (legacy_root / "parsed").glob("CUSTBILL*"):
        stale.unlink()
    incoming.mkdir(parents=True, exist_ok=True)
    (legacy_root / "parsed").mkdir(parents=True, exist_ok=True)
    (legacy_root / "reports").mkdir(parents=True, exist_ok=True)
    for name, content in drops.items():
        (incoming / name).write_bytes(content)


def copybook_psv(dat_bytes: bytes) -> list[str]:
    """The PSV lines copybook CBCUST01 says the parser should emit for these drop-file bytes.

    An independent re-slice of the fixed-width record, used to check the parser's own output rather
    than trust it: `sed` drops `HDR`/`TRL`, `cut -c` addresses bytes (`LC_ALL=C`, so a non-ASCII byte
    is one column, not one character — hence latin-1 here), `awk` trims trailing spaces on
    `CUST-ID`/`CUST-NAME`/`CURRENCY` only, applies the implied decimal as `($4+0)/100` printed
    `%.2f`, and re-punctuates `BILL-DATE` without validating it.
    """
    lines: list[str] = []
    for raw in dat_bytes.decode("latin-1").split("\n"):
        if raw.startswith(("HDR", "TRL")) or raw == "":
            continue
        cust = re.sub(r" +$", "", raw[0:10])
        name = re.sub(r" +$", "", raw[10:40])
        date_raw = raw[40:48]
        amt_raw = raw[48:60]
        currency = re.sub(r" +$", "", raw[60:63])
        rec_type = raw[63:65]
        amt_match = LEADING_NUMBER.match(amt_raw)
        amt = float(amt_match.group(0)) if amt_match else 0.0
        date = f"{date_raw[0:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
        lines.append(f"{cust}|{name}|{date}|{amt / 100:.2f}|{currency}|{rec_type}")
    return lines


def parse_verified(
    legacy_root: pathlib.Path,
    drops: dict[str, bytes],
    faketime: str = FAKETIME,
    attempts: int = 4,
) -> dict[str, object]:
    """Parse until the parser's PSV matches the copybook re-slice of its own inputs.

    The deterministic wrapper preloads libfaketime, and it intermittently fails to attach its
    shared-memory clock in a child process (`ft_shm_init(): sem_open failed`). When that child is one
    of the six `cut`s inside the parser's `paste`, the field group it was slicing comes back empty and
    `paste` shifts the remaining columns — every amount reads `0.00`, or every currency reads empty —
    while the parser's own trailer log still agrees with the detail count and its
    `2>/dev/null || true` swallows the error. Measured at roughly one run in thirty here.

    That corruption would silently become the golden baseline, so the parse is verified against the
    copybook and retried, and the attempt count is reported as evidence rather than hidden.
    """
    expected = {
        name.replace(".dat", ".psv"): copybook_psv(content)
        for name, content in drops.items()
        if name.endswith(".dat")
    }
    mismatches: list[dict[str, object]] = []
    for attempt in range(1, attempts + 1):
        stage(legacy_root, drops)
        counts = parse(legacy_root, faketime)
        actual = {
            path.name: path.read_text(encoding="latin-1").splitlines()
            for path in sorted((legacy_root / "parsed").glob("CUSTBILL*.psv"))
        }
        if actual == expected:
            return {
                "attempts": attempt,
                "rows_per_file": counts,
                "verified_against": "copybook CBCUST01 re-slice of the same drop-file bytes",
                "wrapper_corruption_retries": mismatches,
            }
        mismatches.append(
            {
                "attempt": attempt,
                "files_disagreeing": sorted(
                    name for name in expected if actual.get(name) != expected[name]
                ),
                "first_disagreement": next(
                    (
                        {"file": name, "expected": expected[name][i], "actual": row}
                        for name in sorted(expected)
                        for i, row in enumerate(actual.get(name, []))
                        if i >= len(expected[name]) or row != expected[name][i]
                    ),
                    None,
                ),
            }
        )
    raise LegacyError(
        f"the parser disagreed with copybook CBCUST01 on {attempts} consecutive runs: {mismatches}"
    )


def report(legacy_root: pathlib.Path, faketime: str = FAKETIME) -> dict[str, object]:
    """Run the real Perl report and return the CSV it wrote, plus its `.xls` copy."""
    stdout = _run(["perl", str(REPORT)], legacy_root, faketime)
    csv_path = legacy_root / "reports" / f"finance_billing_{stamp(faketime)}.csv"
    xls_path = csv_path.with_suffix(".xls")
    if not csv_path.exists():
        raise LegacyError(f"the report ran but wrote no {csv_path}: {stdout[-2000:]}")
    csv_text = csv_path.read_text(encoding="latin-1")
    return {
        "csv_path": str(csv_path.relative_to(legacy_root)),
        "csv_text": csv_text,
        "csv_lines": csv_text.splitlines(),
        "xls_exists": xls_path.exists(),
        "xls_identical_to_csv": xls_path.exists()
        and xls_path.read_bytes() == csv_path.read_bytes(),
        "stdout_tail": stdout[-400:],
        "mail_sent": "sendmail" in stdout,
    }


def psv_rows(legacy_root: pathlib.Path) -> list[dict[str, object]]:
    """Every parsed row, in the order the report reads them: `sort @files`, then file order."""
    rows: list[dict[str, object]] = []
    for path in sorted((legacy_root / "parsed").glob("CUSTBILL*.psv")):
        for seq, line in enumerate(path.read_text(encoding="latin-1").splitlines(), start=1):
            fields = line.split("|")
            rows.append(
                {
                    "source_file": path.name,
                    "record_seq": seq,
                    # `split` returns fewer fields on a short line and the rest stay undef; None is
                    # that undef, and it is never coalesced to '' or 0 before the source would.
                    "cust": fields[0] if len(fields) > 0 else None,
                    "bill_date": fields[2] if len(fields) > 2 else None,
                    "amt": fields[3] if len(fields) > 3 else None,
                    "currency": fields[4] if len(fields) > 4 else None,
                    "rec_type": fields[5] if len(fields) > 5 else None,
                }
            )
    return rows


def numify(text: str | None) -> float:
    """Perl's numification of a string in numeric context: leading number, or 0. Never an error."""
    if text is None:
        return 0.0
    match = LEADING_NUMBER.match(text)
    return float(match.group(0)) if match else 0.0


def record_type(rec_type: str | None) -> str:
    """The source's three-way `?:`, including the literal `UNKNOWN(<rt>)` carrying the raw value."""
    if rec_type == "01":
        return "INVOICE"
    if rec_type == "02":
        return "CREDIT"
    return f"UNKNOWN({'' if rec_type is None else rec_type})"


def model(rows: list[dict[str, object]]) -> dict[str, object]:
    """`finance_excel_report.pl` re-expressed: the same population, summed twice.

    `float_total`/`float_text` is what `$tot{$key} += $amt` and `%.2f` produce — one binary-float
    accumulation in the source's own row order, rounded once at print. `exact_total` is the same
    population in `DECIMAL(14,2)`. The difference between them is `ANOM-PERL-ROUNDING`, measured in
    cents; the target carries the exact figure and never the float one.
    """
    float_tot: dict[str, float] = {}
    exact_tot: dict[str, decimal.Decimal] = {}
    counts: dict[str, int] = {}
    skipped_blank_customer = 0
    for row in rows:
        cust = row["cust"]
        # `next if ($cust eq "")`: undef and '' are both '' in that comparison.
        if cust is None or cust == "":
            skipped_blank_customer += 1
            continue
        currency = row["currency"] if row["currency"] is not None else ""
        rec_type = row["rec_type"] if row["rec_type"] is not None else ""
        key = f"{currency}|{rec_type}"
        amt_text = row["amt"]
        float_tot[key] = float_tot.get(key, 0.0) + numify(amt_text)
        exact_tot[key] = exact_tot.get(key, decimal.Decimal(0)) + (
            decimal.Decimal(str(amt_text)) if amt_text not in (None, "") else decimal.Decimal(0)
        )
        counts[key] = counts.get(key, 0) + 1

    groups = []
    # `sort keys %tot` under LC_ALL=C: a byte-wise ascending sort of the composite key.
    for key in sorted(float_tot, key=lambda k: k.encode("latin-1")):
        currency, _, rec_type = key.partition("|")
        exact = exact_tot[key].quantize(CENT)
        float_text = f"{float_tot[key]:.2f}"
        groups.append(
            {
                "legacy_group_key": key,
                "currency": currency,
                "rec_type": rec_type,
                # The report re-splits the key, so a key whose rec_type half is empty reaches the
                # `?:` as undef and prints `UNKNOWN()` — reproduced, not tidied.
                "record_type": record_type(rec_type or None),
                "record_count": counts[key],
                "exact_total": str(exact),
                "float_text": float_text,
                "cent_diff": int(
                    (decimal.Decimal(float_text) - exact).scaleb(2).to_integral_value()
                ),
                "csv_line_exact": f"{currency},{record_type(rec_type or None)},{counts[key]:d},{exact}",
                "csv_line_float": f"{currency},{record_type(rec_type or None)},{counts[key]:d},{float_text}",
            }
        )
    exact_sum = sum((decimal.Decimal(g["exact_total"]) for g in groups), decimal.Decimal(0))
    float_sum = sum((decimal.Decimal(g["float_text"]) for g in groups), decimal.Decimal(0))
    return {
        "rows_read": len(rows),
        "rows_skipped_blank_customer": skipped_blank_customer,
        "rows_contributing": sum(counts.values()),
        "groups": groups,
        "total_exact": str(exact_sum),
        "total_as_printed_by_the_float_accumulator": str(float_sum),
        "total_cent_diff": int((float_sum - exact_sum).scaleb(2).to_integral_value()),
        "groups_with_a_cent_diff": [g["legacy_group_key"] for g in groups if g["cent_diff"]],
        "csv_lines_exact": ["Currency,RecordType,RecordCount,TotalAmount"]
        + [g["csv_line_exact"] for g in groups],
        "csv_lines_float": ["Currency,RecordType,RecordCount,TotalAmount"]
        + [g["csv_line_float"] for g in groups],
    }
