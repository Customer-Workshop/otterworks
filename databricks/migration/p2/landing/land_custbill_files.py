"""Land CUSTBILL*.dat into the governed volume, atomically and idempotently.

Replaces the write half of etl/legacy-extra/jobs/sftp_ingest_poll.ksh:

    s1=`wc -c < $f`; sleep 1; s2=`wc -c < $f`
    if [ "$s1" != "$s2" ]; then ... skipping this pass; fi
    cp $f $INCOMING/$b 2>/dev/null || true
    cp $f $ARCHIVE/$b.`date +%Y%m%d%H%M%S` 2>/dev/null || true
    rm $f 2>/dev/null || true

Four things about that are load-bearing, and three of them are reproduced:

* the double size check is a guess, not a handshake, and it is kept rather than
  dropped. A single PUT makes the *destination* atomic - no reader ever sees a
  partial object - but it says nothing about the source: reading a file the
  producer is still appending to would publish the prefix under the final name,
  permanently. So the source is stat'd before and after the read and a file that
  changed under us is left for the next run instead of being published
  (**P2-D01 - the one accepted behaviour change in pipeline 2 - is that the
  parser can no longer see a partial file, not that the source race is gone; a
  producer that pauses longer than the stability window still defeats both the
  legacy check and this one, and only an upstream rename-on-complete protocol
  would close it. That is D3-01, a STOP E decision.**)
* the archive copy is kept: the landing volume is the archive.
* the delete is not. Nothing removes the producer's file; re-landing an already
  landed file is a no-op, which is what makes the task re-runnable. "Already
  landed" is decided by content digest, not by length: a same-length in-place
  correction is a different file and must not be silently skipped (contract A2).
* `2>/dev/null || true` is not kept. A failed landing fails the task.

Usage:
    python3 land_custbill_files.py --source-dir <dir> [--landing-path /Volumes/...] [--dry-run]
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import json
import os
import sys
import time

DEFAULT_LANDING = "/Volumes/ow_tp/bronze/landing/custbill"
FILE_GLOB = "CUSTBILL*.dat"
STABILITY_WAIT_S = 1.0


def _client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_when_stable(local: str) -> tuple[bytes, bool]:
    """Read the source file and say whether the producer was done with it.

    Returns (payload, stable). The file must be unchanged across a window that
    starts STABILITY_WAIT_S before the read and ends after it: stat, wait, read,
    stat again. Reading first and only then waiting is not enough, because a
    large read can finish inside a producer's pause between writes and the
    prefix would look stable. Publishing a prefix freezes it under the final
    name forever, so anything that moved inside the window is left for the next
    run instead. One retry, then give up on the file.
    """
    for _attempt in (0, 1):
        before = os.stat(local)
        time.sleep(STABILITY_WAIT_S)
        with open(local, "rb") as fh:
            payload = fh.read()
        after = os.stat(local)
        unchanged = (
            before.st_size == after.st_size == len(payload)
            and before.st_mtime_ns == after.st_mtime_ns
        )
        if unchanged:
            return payload, True
    return b"", False


def _landed_digest(w, landing_path: str, name: str) -> str:
    """sha256 of what is already in the landing volume under this name."""
    with w.files.download(f"{landing_path}/{name}").contents as stream:
        return _digest(stream.read())


def _already_landed(w, landing_path: str) -> dict[str, int]:
    """name -> size for what is already in the landing volume."""
    from databricks.sdk.errors import NotFound

    landed: dict[str, int] = {}
    try:
        for entry in w.files.list_directory_contents(landing_path):
            if entry.is_directory:
                continue
            landed[os.path.basename(entry.path)] = entry.file_size or 0
    except NotFound:
        # First landing into this volume. Any other error is fatal: an unreadable
        # landing directory must not be mistaken for an empty one.
        w.files.create_directory(landing_path)
    return landed


def land(source_dir: str, landing_path: str = DEFAULT_LANDING, dry_run: bool = False) -> dict:
    w = None if dry_run else _client()
    landed = {} if dry_run else _already_landed(w, landing_path)

    result = {
        "landing_path": landing_path,
        "landed": [],
        "skipped": [],
        "conflicts": [],
        "unstable": [],
    }
    for name in sorted(os.listdir(source_dir)):
        if not fnmatch.fnmatch(name, FILE_GLOB):
            continue
        local = os.path.join(source_dir, name)
        if not os.path.isfile(local):
            continue

        payload, stable = _read_when_stable(local)
        if not stable:
            # The producer is still writing. Not an error - the next run picks it
            # up - but it must never be published as if it were complete.
            result["unstable"].append({"file": name})
            continue
        size = len(payload)

        if name in landed:
            # Length is not identity: an in-place correction can be the same
            # length and different bytes, and skipping it would leave bronze
            # reporting the superseded figures. Compare the landed bytes.
            if landed[name] == size and (dry_run or _landed_digest(w, landing_path, name) == _digest(payload)):
                # Already landed, same bytes: the legacy would have re-copied and
                # re-archived it under a new timestamp. Skipping is what makes the
                # task re-runnable, and Auto Loader would ignore the duplicate anyway.
                result["skipped"].append({"file": name, "bytes": size})
                continue
            # Same name, different content. Never silently overwrite: the landed
            # copy is what bronze was built from.
            result["conflicts"].append(
                {
                    "file": name,
                    "landed_bytes": landed[name],
                    "source_bytes": size,
                    "reason": "size" if landed[name] != size else "digest",
                }
            )
            continue

        if dry_run:
            result["landed"].append({"file": name, "bytes": size, "dry_run": True})
            continue

        # One PUT. On object-storage-backed volumes the object becomes visible
        # only when the write completes, so no reader can see a partial file.
        w.files.upload(f"{landing_path}/{name}", io.BytesIO(payload), overwrite=False)
        result["landed"].append({"file": name, "bytes": size, "sha256": _digest(payload)})

    if result["conflicts"]:
        raise SystemExit(
            "landing conflict, nothing overwritten: "
            + json.dumps(result["conflicts"])
        )
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-dir", required=True)
    ap.add_argument("--landing-path", default=DEFAULT_LANDING)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    result = land(args.source_dir, args.landing_path, args.dry_run)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
