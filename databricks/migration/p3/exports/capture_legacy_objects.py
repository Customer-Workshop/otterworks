"""Freeze the legacy report objects for a pinned run date as bytes, for the byte gate.

    AWS_ENDPOINT_URL=http://localhost:4566 \
    python3 databricks/migration/p3/exports/capture_legacy_objects.py \
        --unit p3-analytics-daily --run-date 2026-09-15

The recon baselines under `.migration/recon/p3/baselines/` carry each object's digest and
its *parsed* content, and parsing loses what the gate is about: `json.dumps` writes keys in
insertion order, and the legacy never sorts the inner dicts, so a target that agrees on
every number can still write different bytes. This writes the bytes themselves, base64'd,
into a manifest the comparison and the offline self-test both read.

It reads the legacy estate's own S3 (`AWS_ENDPOINT_URL` is required -- without it boto3
resolves to real AWS) and refuses to record an object whose digest does not match the one
the captured baseline recorded, so the manifest cannot drift away from the run the recon
evidence was taken from. `report.json` is the one exception: it embeds
`datetime.now()`, so it is verified against the baseline modulo `generated_at` and the
legacy's own value is recorded next to it.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASELINES = ROOT / ".migration/recon/p3/baselines"
HERE = Path(__file__).resolve().parent / "legacy_objects"

# A unit joins this table in the PR that restores its export, not before.
UNITS = {
    "p3-analytics-daily": {"bucket": "otterworks-data-lake",
                           "export_root": "/Volumes/ow_tp/gold/exports/analytics",
                           "wallclock_key_suffix": "report.json",
                           "wallclock_field": "generated_at"},
    "p3-user-activity": {"bucket": "otterworks-data-lake",
                         "export_root": "/Volumes/ow_tp/gold/exports/user-activity",
                         "wallclock_key_suffix": "activity_report.json",
                         "wallclock_field": "generated_at"},
}


def normalized_digest(body: bytes, field: str, value: str) -> str:
    obj = json.loads(body.decode("utf-8"))
    obj[field] = value
    return hashlib.sha256(json.dumps(obj, indent=2).encode("utf-8")).hexdigest()


def capture(unit: str, run_date: str) -> dict:
    import boto3

    if not os.environ.get("AWS_ENDPOINT_URL"):
        raise SystemExit(
            "AWS_ENDPOINT_URL is unset. Without it boto3 talks to real AWS instead of the "
            "legacy estate; set it, e.g. AWS_ENDPOINT_URL=http://localhost:4566.")
    spec = UNITS[unit]
    baseline = json.loads((BASELINES / f"{unit}.baseline.json").read_text())
    s3 = boto3.client("s3", endpoint_url=os.environ["AWS_ENDPOINT_URL"])

    objects, problems = {}, []
    for key, recorded in sorted(baseline["outputs"].items()):
        body = s3.get_object(Bucket=spec["bucket"], Key=key)["Body"].read()
        digest = hashlib.sha256(body).hexdigest()
        entry = {"bytes": len(body), "sha256": digest,
                 "raw_b64": base64.b64encode(body).decode("ascii")}
        if key.endswith(spec["wallclock_key_suffix"]):
            entry["wallclock_field"] = spec["wallclock_field"]
            entry["wallclock_value"] = json.loads(body.decode())[spec["wallclock_field"]]
            entry["baseline_sha256_at_baseline_wallclock"] = recorded["sha256"]
            # The baseline parsed some of these objects and only digested others. Where it
            # kept the content, the object is checked modulo the wall clock; where it kept
            # only a digest, that digest is of these very bytes and has to match exactly.
            if recorded.get("content"):
                legacy_value = recorded["content"][spec["wallclock_field"]]
                if normalized_digest(body, spec["wallclock_field"], legacy_value) \
                        != recorded["sha256"]:
                    problems.append(
                        f"{key}: differs from the captured baseline by more than "
                        f"{spec['wallclock_field']}")
            elif digest != recorded["sha256"]:
                problems.append(
                    f"{key}: estate object sha256 {digest} != baseline "
                    f"{recorded['sha256']}")
        elif digest != recorded["sha256"]:
            problems.append(
                f"{key}: estate object sha256 {digest} != baseline {recorded['sha256']}")
        objects[key] = entry

    if problems:
        raise SystemExit("\n".join(problems))
    return {
        "unit": unit,
        "run_date": run_date,
        "bucket": spec["bucket"],
        "export_root": spec["export_root"],
        "source": f".migration/recon/p3/baselines/{unit}.baseline.json and the legacy "
                  "estate's own S3 objects for this run date",
        "objects": objects,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", required=True, choices=sorted(UNITS))
    ap.add_argument("--run-date", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    manifest = capture(args.unit, args.run_date)
    out = Path(args.out) if args.out else HERE / f"{args.unit}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"{out}: {len(manifest['objects'])} objects", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
