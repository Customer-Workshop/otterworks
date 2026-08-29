#!/usr/bin/env python3
"""Run the bronze_custbill unit end to end and emit its recon report.

Executes the pipeline's own statements (imported from
``notebooks/bronze_custbill.py`` — no second copy of the logic) on the existing
serverless SQL warehouse, twice, then recomputes every reported number from the
target tables and compares the surviving population against the legacy parser's
`.psv` output. Nothing here creates compute.

Credentials come from ``DATABRICKS_HOST``/``DATABRICKS_TOKEN``, falling back to
``DATABRICKS_DEMO_HOST``/``DATABRICKS_DEMO_TOKEN``. No value is printed.

Usage:
  run_bronze_custbill.py --ns demo \
      --landing-source <dir of CUSTBILL*.dat> \
      --baseline <legacy $ROOT/parsed dir> \
      --out bronze_custbill.recon.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import pathlib
import posixpath
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

HERE = pathlib.Path(__file__).resolve().parent
NOTEBOOK = HERE.parent / "notebooks" / "bronze_custbill.py"
WAREHOUSE_NAME = os.environ.get("OW_TP_WAREHOUSE", "Serverless Starter Warehouse")
QUARANTINE_HALT_PCT = Decimal("5")

# Everything this recon does not prove, stated rather than implied.
UNVERIFIED_PATHS = [
    "Databricks Workflows job ow_tp_bronze_custbill was not triggered: the job is declared in "
    "infrastructure/terraform-databricks/jobs_bronze_custbill.tf and the parent applies the stack, so the "
    "notebook's statements were executed against the same serverless SQL warehouse instead of "
    "through a job run.",
    "The legacy ingest poll (sftp_ingest_poll.ksh) was run without libfaketime: ksh segfaults under "
    "the LD_PRELOAD, so only TZ=UTC/LC_ALL=C were pinned for that step. It contributes no value to "
    "the parsed output, only archive-copy timestamps. The parse step that produces the golden "
    "baseline ran with the frozen clock.",
    "Unity Catalog column masks over cust_id/cust_name are parent-owned (PII lands in cleartext here "
    "by design) and were not created or asserted by this unit.",
]


def _load_pipeline():
    """Import the notebook module so the recon runs the shipped SQL verbatim."""
    spec = importlib.util.spec_from_file_location("bronze_custbill_pipeline", NOTEBOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pipeline = _load_pipeline()


class DatabricksError(RuntimeError):
    pass


def _host() -> str:
    host = os.environ.get("DATABRICKS_HOST") or os.environ.get("DATABRICKS_DEMO_HOST")
    if not host:
        raise DatabricksError("DATABRICKS_HOST (or DATABRICKS_DEMO_HOST) is not set")
    return host.rstrip("/")


def _token() -> str:
    token = os.environ.get("DATABRICKS_TOKEN") or os.environ.get("DATABRICKS_DEMO_TOKEN")
    if not token:
        raise DatabricksError("DATABRICKS_TOKEN (or DATABRICKS_DEMO_TOKEN) is not set")
    return token


def request(method: str, path: str, body: dict | None = None, raw: bytes | None = None) -> dict:
    headers = {"Authorization": f"Bearer {_token()}"}
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif raw is not None:
        headers["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(_host() + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as exc:
        raise DatabricksError(f"{method} {path} -> {exc.code}: {exc.read().decode()[:800]}") from exc
    return json.loads(payload) if payload else {}


_WAREHOUSE_ID: str | None = None


def warehouse_id() -> str:
    global _WAREHOUSE_ID
    if _WAREHOUSE_ID is None:
        for warehouse in request("GET", "/api/2.0/sql/warehouses").get("warehouses", []):
            if warehouse["name"] == WAREHOUSE_NAME:
                _WAREHOUSE_ID = warehouse["id"]
                break
        else:
            raise DatabricksError(f"serverless warehouse {WAREHOUSE_NAME!r} not found (never create one)")
    return _WAREHOUSE_ID


def sql(statement: str, timeout_s: int = 1800) -> list[list[str | None]]:
    result = request(
        "POST",
        "/api/2.0/sql/statements",
        {
            "warehouse_id": warehouse_id(),
            "statement": statement,
            "wait_timeout": "50s",
            "on_wait_timeout": "CONTINUE",
        },
    )
    deadline = time.time() + timeout_s
    while result["status"]["state"] in ("PENDING", "RUNNING"):
        if time.time() >= deadline:
            raise DatabricksError(f"statement still running after {timeout_s}s")
        time.sleep(2)
        result = request("GET", f"/api/2.0/sql/statements/{result['statement_id']}")
    if result["status"]["state"] != "SUCCEEDED":
        message = result["status"].get("error", {}).get("message", result["status"]["state"])
        raise DatabricksError(f"statement failed: {message}\n  {statement[:400]}")
    rows = list((result.get("result") or {}).get("data_array") or [])
    next_link = (result.get("result") or {}).get("next_chunk_internal_link")
    while next_link:
        chunk = request("GET", next_link)
        rows.extend((chunk.get("result") or chunk).get("data_array") or [])
        next_link = (chunk.get("result") or chunk).get("next_chunk_internal_link")
    return rows


def upload(local: pathlib.Path, volume_path: str) -> None:
    request(
        "PUT",
        f"/api/2.0/fs/files{urllib.parse.quote(volume_path)}?overwrite=true",
        raw=local.read_bytes(),
    )


def list_landing(prefix: str) -> list[str]:
    """Names under the unit's landing prefix; a missing prefix is a quiet poll."""
    try:
        entries = request("GET", "/api/2.0/fs/directories" + urllib.parse.quote(prefix))
    except DatabricksError as exc:
        if "404" in str(exc) or "NOT_FOUND" in str(exc):
            return []
        raise
    return [e["name"] for e in entries.get("contents", [])]


# --------------------------------------------------------------------------- #
# legacy golden baseline
# --------------------------------------------------------------------------- #


def read_baseline(parsed_dir: pathlib.Path) -> dict[tuple[str, int], dict[str, str]]:
    """Load the legacy parser's `.psv` output keyed by (source_file, record_seq)."""
    baseline: dict[tuple[str, int], dict[str, str]] = {}
    for psv in sorted(parsed_dir.glob("CUSTBILL*.psv")):
        source_file = psv.stem + ".dat"
        for seq, line in enumerate(psv.read_bytes().decode("latin-1").splitlines(), start=1):
            fields = line.split("|")
            baseline[(source_file, seq)] = {
                "cust_id": fields[0],
                "cust_name": fields[1],
                "bill_date": fields[2],
                "bill_amt": fields[3],
                "currency": fields[4],
                "rec_type": fields[5],
            }
    return baseline


# --------------------------------------------------------------------------- #
# evidence gathering
# --------------------------------------------------------------------------- #


def run_load(ns: str) -> dict:
    """Run the pipeline exactly as the job runs it, honouring the empty-poll no-op."""
    prefix = pipeline.landing_prefix(ns)
    landed = [n for n in list_landing(prefix) if n.endswith(".dat")]
    if not landed:
        return {"files_seen": 0, "statements": [], "no_op": True}
    executed = []
    for label, statement in pipeline.load_statements(ns):
        sql(statement)
        executed.append(label)
    return {"files_seen": len(landed), "statements": executed, "no_op": False}


def totals(ns: str) -> dict:
    row = sql(pipeline.target_totals(ns))[0]
    return {
        "loaded_rows": int(row[0]),
        "quarantined_rows": int(row[1]),
        "bill_amt_total": str(Decimal(row[2])),
        "loaded_checksum": row[3],
        "quarantine_checksum": row[4],
    }


def table_version(table: str) -> int:
    return int(sql(f"DESCRIBE HISTORY {table} LIMIT 1")[0][0])


def merge_metrics_since(table: str, from_version: int) -> dict:
    """Rows written to a target table by commits newer than ``from_version``."""
    written = {"numTargetRowsInserted": 0, "numTargetRowsUpdated": 0, "numTargetRowsDeleted": 0}
    for row in sql(f"DESCRIBE HISTORY {table}"):
        if int(row[0]) <= from_version:
            continue
        for cell in row:
            if cell and cell.strip().startswith("{") and "numTargetRows" in cell:
                metrics = json.loads(cell)
                for key in written:
                    written[key] += int(metrics.get(key, 0))
                break
    return written


def check(cid: str, expected, actual, source: str) -> dict:
    return {
        "id": cid,
        "expected": expected,
        "actual": actual,
        "source_of_truth": source,
        "result": "pass" if expected == actual else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ns", default="demo")
    parser.add_argument("--landing-source", type=pathlib.Path, required=True)
    parser.add_argument("--baseline", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument(
        "--empty-poll-ns",
        default="demo_emptypoll",
        help="namespace with no landed files, used to exercise empty_input_semantics",
    )
    args = parser.parse_args()

    # Fail fast on a malformed namespace: ns is this run's isolation boundary in a
    # workspace other runs share, as well as the only value spliced into the SQL.
    ns = pipeline.validate_ns(args.ns)
    pipeline.validate_ns(args.empty_poll_ns)
    prefix = pipeline.landing_prefix(ns)
    provenance: dict[str, object] = {
        "landing_prefix": prefix,
        "records_table": pipeline.RECORDS_TABLE,
        "quarantine_table": pipeline.QUARANTINE_TABLE,
        "warehouse": WAREHOUSE_NAME,
        "pipeline_source": "pipelines/databricks/bronze_custbill/notebooks/bronze_custbill.py",
        "golden_baseline": (
            "legacy parse_custbill_fixedwidth.sh output under $OTTERWORKS_LEGACY_ROOT/parsed, "
            "produced through scripts/tp-run-deterministic.sh (TZ=UTC, LC_ALL=C)"
        ),
    }

    # 1. land the drop files exactly as the SFTP poll would, plus the transfer
    #    marker that tells the pipeline the transfer finished.
    if not args.skip_upload:
        landed = []
        for path in sorted(args.landing_source.glob("*")):
            if not path.is_file():
                continue
            upload(path, posixpath.join(prefix, path.name))
            landed.append(path.name)
        provenance["landed_files"] = landed
    provenance["landing_contents"] = sorted(list_landing(prefix))

    # 2. two identical runs: the second must be a no-op.
    first = run_load(ns)
    after_first = totals(ns)
    records_version = table_version(pipeline.RECORDS_TABLE)
    quarantine_version = table_version(pipeline.QUARANTINE_TABLE)
    second = run_load(ns)
    after_second = totals(ns)
    records_metrics = merge_metrics_since(pipeline.RECORDS_TABLE, records_version)
    quarantine_metrics = merge_metrics_since(pipeline.QUARANTINE_TABLE, quarantine_version)
    provenance["first_run"] = first
    provenance["second_run"] = second

    # 3. recompute everything from the target and the landing prefix.
    census = [
        {
            "source_file": r[0],
            "trailer_count": None if r[1] is None else int(r[1]),
            "detail_count": int(r[2]),
            "trailer_matches": r[3] == "true",
            "transfer_marker_matches": r[4] == "true",
        }
        for r in sql(pipeline.file_census(ns))
    ]
    population = [(r[0], int(r[1]), r[2]) for r in sql(pipeline.source_population(ns))]
    loaded = [
        {
            "source_file": r[0],
            "record_seq": int(r[1]),
            "cust_id": r[2],
            "cust_name": r[3],
            "bill_date": r[4],
            "bill_amt": r[5],
            "currency": r[6],
            "rec_type": r[7],
            "raw_overflow": r[8],
            "overflow_flag": r[9] == "true",
            "record_bytes": int(r[10]),
        }
        for r in sql(pipeline.loaded_rows(ns))
    ]
    quarantined = [
        {
            "source_file": r[0],
            "record_seq": int(r[1]),
            "quarantine_reason": r[2],
            "legacy_bill_amt": r[3],
            "legacy_bill_date": r[4],
            "record_bytes": int(r[5]),
            "raw_record": r[6],
        }
        for r in sql(pipeline.quarantined_rows(ns))
    ]
    money_columns = [
        {"table": r[0], "column": r[1], "type": r[2]} for r in sql(pipeline.money_column_types())
    ]
    ns_gaps = int(
        sql(
            f"SELECT (SELECT count(*) FROM {pipeline.RECORDS_TABLE} WHERE ns IS NULL OR ns <> '{ns}') "
            f"+ (SELECT count(*) FROM {pipeline.QUARANTINE_TABLE} WHERE ns IS NULL OR ns <> '{ns}')"
        )[0][0]
    )
    control_rows = int(
        sql(
            f"SELECT count(*) FROM {pipeline.RECORDS_TABLE} "
            f"WHERE ns = '{ns}' AND (raw_record LIKE 'HDR%' OR raw_record LIKE 'TRL%')"
        )[0][0]
    )

    # 4. empty poll: same code path, a namespace with nothing landed.
    empty = run_load(args.empty_poll_ns)
    after_empty = totals(ns)

    # 5. compare the surviving population against the legacy parser's own output.
    baseline = read_baseline(args.baseline)
    ingested_files = {f["source_file"] for f in census if f["trailer_matches"] and f["transfer_marker_matches"]}
    source_rows = len(population)
    loaded_rows_n = len(loaded)
    quarantined_rows_n = len(quarantined)

    parity_mismatches = []
    baseline_money = Decimal("0.00")
    for row in loaded:
        key = (row["source_file"], row["record_seq"])
        want = baseline.get(key)
        if want is None:
            parity_mismatches.append({"key": list(key), "reason": "absent from legacy baseline"})
            continue
        baseline_money += Decimal(want["bill_amt"])
        got = {
            "cust_id": row["cust_id"] or "",
            "cust_name": row["cust_name"] or "",
            "bill_date": row["bill_date"],
            "bill_amt": str(Decimal(row["bill_amt"])),
            "currency": row["currency"] or "",
            "rec_type": row["rec_type"],
        }
        expected = dict(want)
        if got != expected:
            parity_mismatches.append({"key": list(key), "legacy": expected, "target": got})

    legacy_divergences = []
    for row in quarantined:
        want = baseline.get((row["source_file"], row["record_seq"]))
        legacy_amt = None if want is None else want["bill_amt"]
        legacy_date = None if want is None else want["bill_date"]
        legacy_replay_matches = (
            want is not None
            and Decimal(row["legacy_bill_amt"]) == Decimal(legacy_amt)
            and row["legacy_bill_date"] == legacy_date
        )
        legacy_divergences.append(
            {
                "source_file": row["source_file"],
                "record_seq": row["record_seq"],
                "quarantine_reason": row["quarantine_reason"],
                "legacy_value_loaded_by_source": {"bill_amt": legacy_amt, "bill_date": legacy_date},
                "legacy_value_recorded_in_quarantine": {
                    "bill_amt": row["legacy_bill_amt"],
                    "bill_date": row["legacy_bill_date"],
                },
                "legacy_replay_matches": legacy_replay_matches,
            }
        )

    baseline_rows_not_ingested = sorted(
        f"{f}#{s}" for (f, s) in baseline if f not in ingested_files
    )
    reasons = sorted({row["quarantine_reason"] for row in quarantined})
    quarantine_rate = (
        (Decimal(quarantined_rows_n) * 100 / Decimal(source_rows)).quantize(Decimal("0.01"))
        if source_rows
        else Decimal("0.00")
    )

    trailer_reconciliation = [
        {
            "source_file": f["source_file"],
            "trailer_count": f["trailer_count"],
            "loaded_plus_quarantined": sum(1 for p in population if p[0] == f["source_file"]),
            "ingested": f["source_file"] in ingested_files,
            "rejected_because": (
                None
                if f["source_file"] in ingested_files
                else (
                    "no matching completed-transfer marker: the file may still be being written"
                    if not f["transfer_marker_matches"]
                    else "trailer count disagrees with detail count"
                )
            ),
        }
        for f in census
    ]

    detections = {
        # The implied decimal is only demonstrably honoured if no loaded row
        # disagrees with the legacy two-decimal value and at least one row
        # carries non-zero cents (an integer read would have inflated it 100x).
        "ANOM-IMPLIED-DECIMAL": bool(loaded)
        and not parity_mismatches
        and any(Decimal(row["bill_amt"]) % 1 != 0 for row in loaded),
        "ANOM-NONNUMERIC-AMT": "AMT_NON_NUMERIC" in reasons,
        "ANOM-INVALID-DATE": "DATE_INVALID" in reasons,
        "ANOM-TRAILER-MISMATCH": any(not f["trailer_matches"] for f in census),
        "ANOM-SHORT-RECORD": "RECORD_SHORT" in reasons,
    }
    expected_set = sorted(detections)
    actual_set = sorted(k for k, v in detections.items() if v)

    checks = [
        check(
            "ACC-MONEY",
            {
                "bill_amt_total": str(baseline_money),
                "double_or_float_columns_anywhere_in_the_unit": 0,
                "typed_money_column_types": ["decimal(14,2)"],
            },
            {
                "bill_amt_total": after_second["bill_amt_total"],
                "double_or_float_columns_anywhere_in_the_unit": sum(
                    1 for c in money_columns if c["type"].lower() in ("double", "float")
                ),
                # bill_amt_raw / legacy_bill_date stay STRING on purpose: they hold
                # the source bytes, not a monetary value.
                "typed_money_column_types": sorted(
                    {c["type"].lower() for c in money_columns if c["column"] in ("bill_amt", "legacy_bill_amt")}
                ),
            },
            "legacy .psv BILL-AMT column summed as Decimal vs sum(bill_amt) recomputed from the target",
        ),
        check(
            "ACC-QUAR",
            {"source_rows": source_rows, "halt_threshold_pct": str(QUARANTINE_HALT_PCT), "over_threshold": False},
            {
                "source_rows": loaded_rows_n + quarantined_rows_n,
                "halt_threshold_pct": str(QUARANTINE_HALT_PCT),
                "over_threshold": quarantine_rate > QUARANTINE_HALT_PCT,
            },
            "count(*) on both target tables vs the detail-record population of the ingested files",
        ),
        check(
            "ACC-IDEM",
            {
                "loaded_rows": after_first["loaded_rows"],
                "quarantined_rows": after_first["quarantined_rows"],
                "bill_amt_total": after_first["bill_amt_total"],
                "loaded_checksum": after_first["loaded_checksum"],
                "quarantine_checksum": after_first["quarantine_checksum"],
                "second_run_rows_written": 0,
            },
            {
                "loaded_rows": after_second["loaded_rows"],
                "quarantined_rows": after_second["quarantined_rows"],
                "bill_amt_total": after_second["bill_amt_total"],
                "loaded_checksum": after_second["loaded_checksum"],
                "quarantine_checksum": after_second["quarantine_checksum"],
                "second_run_rows_written": sum(records_metrics.values()) + sum(quarantine_metrics.values()),
            },
            "target totals and md5 payload checksums after run 1 vs run 2, plus DESCRIBE HISTORY MERGE metrics",
        ),
        check(
            "ACC-NS",
            {"rows_with_foreign_or_null_ns": 0, "landing_prefix": prefix, "ns": ns},
            {"rows_with_foreign_or_null_ns": ns_gaps, "landing_prefix": prefix, "ns": ns},
            "count(*) filtered on ns in both target tables; landing prefix used by the pipeline",
        ),
        check(
            "ACC-IMPLIED-DEC",
            {"rows_disagreeing_with_legacy_psv": 0, "rows_compared": len(loaded)},
            {"rows_disagreeing_with_legacy_psv": len(parity_mismatches), "rows_compared": len(loaded)},
            "field-by-field comparison of every loaded row against its legacy .psv line",
        ),
        check(
            "ACC-NONNUMERIC-AMT",
            {
                "quarantined": True,
                "legacy_zero_adopted_as_truth": False,
                "legacy_value_replayed_exactly": True,
            },
            {
                "quarantined": "AMT_NON_NUMERIC" in reasons,
                "legacy_zero_adopted_as_truth": any(
                    row["quarantine_reason"] == "AMT_NON_NUMERIC"
                    and (row["source_file"], row["record_seq"])
                    in {(l["source_file"], l["record_seq"]) for l in loaded}
                    for row in quarantined
                ),
                "legacy_value_replayed_exactly": all(
                    d["legacy_replay_matches"]
                    for d in legacy_divergences
                    if d["quarantine_reason"] == "AMT_NON_NUMERIC"
                )
                and any(d["quarantine_reason"] == "AMT_NON_NUMERIC" for d in legacy_divergences),
            },
            "quarantine table rows vs the legacy .psv value for the same record",
        ),
        check(
            "ACC-BILL-DATE",
            {"impossible_dates_quarantined": True, "impossible_dates_landed": 0},
            {
                "impossible_dates_quarantined": "DATE_INVALID" in reasons,
                "impossible_dates_landed": sum(
                    1 for row in loaded if row["bill_date"] in (None, "", "0000-00-00")
                ),
            },
            "quarantine reasons recomputed from the target vs bill_date values in the records table",
        ),
        check(
            "ACC-HDR-TRL",
            {
                "control_records_loaded": 0,
                "files_with_trailer_mismatch_ingested": 0,
                "trailer_reconciles_for_every_ingested_file": True,
            },
            {
                "control_records_loaded": control_rows,
                "files_with_trailer_mismatch_ingested": sum(
                    1 for f in trailer_reconciliation if f["ingested"] and f["trailer_count"] != f["loaded_plus_quarantined"]
                ),
                "trailer_reconciles_for_every_ingested_file": all(
                    f["trailer_count"] == f["loaded_plus_quarantined"]
                    for f in trailer_reconciliation
                    if f["ingested"]
                ),
            },
            "TRL positions 4-13 per file vs loaded+quarantined rows for that file, recomputed from the target",
        ),
        check(
            "ACC-PARTIAL-FILE",
            {"files_without_matching_marker_ingested": 0},
            {
                "files_without_matching_marker_ingested": sum(
                    1
                    for f in census
                    if not f["transfer_marker_matches"]
                    and any(row["source_file"] == f["source_file"] for row in loaded + quarantined)
                )
            },
            "landing census vs the source_file values present in the target tables",
        ),
        check(
            "EMPTY-POLL-NOOP",
            {
                "files_seen": 0,
                "statements_executed": [],
                "loaded_rows": after_second["loaded_rows"],
                "loaded_checksum": after_second["loaded_checksum"],
            },
            {
                "files_seen": empty["files_seen"],
                "statements_executed": empty["statements"],
                "loaded_rows": after_empty["loaded_rows"],
                "loaded_checksum": after_empty["loaded_checksum"],
            },
            f"pipeline run against landing prefix {pipeline.landing_prefix(args.empty_poll_ns)} (no files), "
            "then the ns=" + ns + " totals re-read from the target",
        ),
    ]

    # A green unit can still leave files on the floor: refusing a file is the
    # correct outcome, but somebody has to chase the drop. Surfaced rather than
    # left to be inferred from the file lists.
    operator_action_required = [
        {
            "source_file": f["source_file"],
            "why_not_ingested": f["rejected_because"],
            "trailer_count": f["trailer_count"],
            "rows_in_this_file_not_in_the_target": sum(
                1 for row in baseline_rows_not_ingested if row.startswith(f["source_file"] + "#")
            ),
            "action": (
                "ask the sender to redeliver the file with a completed-transfer marker; "
                "the pipeline picks it up on the next poll with no cleanup needed"
                if not next(c["transfer_marker_matches"] for c in census if c["source_file"] == f["source_file"])
                else "reconcile the TRL count with the sender before redelivery; "
                "the file is refused whole, so no partial rows need removing"
            ),
        }
        for f in trailer_reconciliation
        if not f["ingested"]
    ]

    failed = [c["id"] for c in checks if c["result"] == "fail"]
    missing = [a for a in expected_set if a not in actual_set]
    if quarantine_rate > QUARANTINE_HALT_PCT:
        recon_result = "halted"
    elif failed or missing:
        recon_result = "red"
    else:
        recon_result = "green"

    report = {
        "kind": "recon-report",
        "unit": pipeline.UNIT,
        "namespace": ns,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        ),
        "run_mode": "live",
        "recon_result": recon_result,
        "values_recomputed_from_target": True,
        # Read this before the counts: green means every ingested row reconciles,
        # not that every landed file was ingested.
        "operator_action_required": {
            "files_not_ingested": len(operator_action_required),
            "rows_not_in_the_target": len(baseline_rows_not_ingested),
            "items": operator_action_required,
        },
        "provenance": provenance,
        "counts": {
            "files_seen": len(census),
            "files_ingested": sorted(ingested_files),
            "files_rejected": [f for f in trailer_reconciliation if not f["ingested"]],
            "source_rows": source_rows,
            "loaded_rows": loaded_rows_n,
            "quarantined_rows": quarantined_rows_n,
            "accounting_identity": f"{loaded_rows_n} + {quarantined_rows_n} == {source_rows}",
            "quarantine_rate_pct": str(quarantine_rate),
            "quarantine_halt_threshold_pct": str(QUARANTINE_HALT_PCT),
            "quarantine_by_reason": {
                reason: sum(1 for row in quarantined if row["quarantine_reason"] == reason)
                for reason in reasons
            },
        },
        "money": {
            "column_type": "DECIMAL(14,2)",
            "bill_amt_total_target": after_second["bill_amt_total"],
            "bill_amt_total_legacy_baseline": str(baseline_money),
            "quarantined_rows_alongside_money": quarantined_rows_n,
            "quarantined_money_withheld_from_total": str(
                sum((Decimal(d["legacy_value_loaded_by_source"]["bill_amt"] or "0") for d in legacy_divergences),
                    Decimal("0.00"))
            ),
        },
        "trailer_reconciliation": trailer_reconciliation,
        "legacy_divergences": legacy_divergences,
        "legacy_baseline_rows_outside_target_population": {
            "count": len(baseline_rows_not_ingested),
            "rows": baseline_rows_not_ingested,
            "why": (
                "the legacy parser loads every detail record of every file it finds; these belong to files "
                "this unit refused to ingest (trailer mismatch, or no completed-transfer marker)"
            ),
        },
        "parity_mismatches": parity_mismatches,
        "idempotency_rerun": {
            "performed": True,
            "result": "pass" if next(c for c in checks if c["id"] == "ACC-IDEM")["result"] == "pass" else "fail",
            "evidence": (
                f"run 1 loaded={after_first['loaded_rows']} quarantined={after_first['quarantined_rows']} "
                f"total={after_first['bill_amt_total']} checksum={after_first['loaded_checksum']}; "
                f"run 2 loaded={after_second['loaded_rows']} quarantined={after_second['quarantined_rows']} "
                f"total={after_second['bill_amt_total']} checksum={after_second['loaded_checksum']}; "
                f"latest MERGE metrics records={records_metrics} quarantine={quarantine_metrics}"
            ),
        },
        "planted_anomaly_detections": {
            "expected_set": expected_set,
            "actual_set": actual_set,
            "missing": missing,
            "unexpected": [a for a in actual_set if a not in expected_set],
        },
        "checks": checks,
        "unverified_paths": UNVERIFIED_PATHS,
    }
    args.out.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n")
    print(f"wrote {args.out} recon_result={recon_result}")
    print(json.dumps(report["counts"], indent=2))
    if failed:
        print(f"FAILED checks: {failed}", file=sys.stderr)
    if missing:
        print(f"UNDETECTED anomalies: {missing}", file=sys.stderr)
    return 0 if recon_result == "green" else 1


if __name__ == "__main__":
    raise SystemExit(main())
