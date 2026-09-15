"""Write the finance close to a volume as the CSV the Perl wrote, and as its `.xls` twin.

Replaces the output half of etl/legacy-extra/jobs/finance_excel_report.pl: the same
bytes, at a governed path, with the mail step gone. Run as a serverless job task:

    python finance_close_export.py --stamp 20260915

`--stamp` names the day in the file name, the way the Perl's `localtime` did. It
defaults to today in UTC rather than in a box's local timezone, because the ETL box's
clock is not something the target can reproduce; the orchestration job passes the
stamp explicitly. Rerunning with the same stamp overwrites the same two files with
the same bytes, so the task is idempotent.

The `.xls` is a byte copy of the CSV, not a spreadsheet. That is what the legacy did
(`cp $csv $xls`, "do not judge us") and repointing anything that reads it is a user
decision at STOP E, not a migration one (C-7.7, D4-01). The sendmail pipe is *not*
reproduced: it has been dead for years, and the job's failure notification replaces it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import os
import pathlib
import sys

ENCODING = "iso-8859-1"
GOLD_TABLE = "ow_tp.gold.custbill_finance_close"
EXPORT_DIR = "/Volumes/ow_tp/gold/exports/custbill"


def load_render_csv(pipeline_dir: str | None = None):
    """The shared renderer, from the pipeline directory that sits next to this file.

    A serverless `spark_python_task` runs the file through `exec(compile(...))`, so
    `__file__` is not defined and the location has to be handed in; the job passes
    `${workspace.file_path}/pipeline`. Run locally, the sibling directory is found.

    Overriding the run's parameters replaces them all, so `--pipeline-dir` is easy to
    drop by accident; that is worth a sentence rather than a KeyError on `__file__`.
    """
    if pipeline_dir is None:
        if "__file__" not in globals():
            raise RuntimeError(
                "--pipeline-dir is required when this file is exec()'d without __file__ "
                "(a serverless python task); pass ${workspace.file_path}/pipeline"
            )
        pipeline_dir = str(pathlib.Path(globals()["__file__"]).resolve().parents[1] / "pipeline")
    sys.path.insert(0, pipeline_dir)
    return importlib.import_module("custbill_close").render_csv


def report_rows(spark) -> list[dict]:
    """Gold, in the report's order: `sort keys %tot` over `"$ccy|$rt"`, as strings."""
    rows = (
        spark.read.table(GOLD_TABLE)
        .select("currency", "record_type", "record_count", "total_amount", "sort_key")
        .collect()
    )
    return [
        {
            "currency": row["currency"],
            "record_type": row["record_type"],
            "record_count": row["record_count"],
            "total_amount": float(row["total_amount"]),
        }
        for row in sorted(rows, key=lambda row: row["sort_key"])
    ]


def write_report(spark, stamp: str, export_dir: str, pipeline_dir: str | None = None) -> list[str]:
    render_csv = load_render_csv(pipeline_dir)
    body = render_csv(report_rows(spark)).encode(ENCODING)
    os.makedirs(export_dir, exist_ok=True)
    written = []
    for suffix in ("csv", "xls"):
        path = f"{export_dir}/finance_billing_{stamp}.{suffix}"
        with open(path, "wb") as handle:
            handle.write(body)
        written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stamp", default=dt.datetime.now(tz=dt.timezone.utc).strftime("%Y%m%d"))
    parser.add_argument("--export-dir", default=EXPORT_DIR)
    parser.add_argument("--pipeline-dir", default=None)
    args = parser.parse_args()

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    for path in write_report(spark, args.stamp, args.export_dir, args.pipeline_dir):
        print(f"wrote {path}")


if __name__ == "__main__":
    # Called, not `raise SystemExit(main())`: a serverless python task is exec()'d
    # inside a notebook kernel, which reports even SystemExit(0) as a failed run.
    main()
