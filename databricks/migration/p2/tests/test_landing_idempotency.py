"""Fixture-first checks for the landing rules: source stability and content identity.

Run: python3 databricks/migration/p2/tests/test_landing_idempotency.py

Both rules exist because a landed object is permanent: `overwrite=False` means a
prefix published from a file still being written can never be repaired, and a
same-length in-place correction that is skipped leaves bronze reporting the
superseded figures (contract A2, per-file byte equality).
"""

from __future__ import annotations

import builtins
import hashlib
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "databricks/migration/p2/landing"))

import land_custbill_files as landing

# The real one-second window is the point of the helper, but waiting it out four
# times buys nothing here; every test drives the producer by hand.
landing.STABILITY_WAIT_S = 0

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"ok   {name}")
    else:
        failures.append(f"{name}: {detail}")
        print(f"FAIL {name}: {detail}")


class FakeWorkspace:
    """Just enough of WorkspaceClient.files for the landing rules."""

    def __init__(self, contents: dict[str, bytes]):
        self.contents = dict(contents)
        self.uploads: list[str] = []

    def _list(self, landing_path):
        class Entry:
            def __init__(self, path, size):
                self.path = path
                self.file_size = size
                self.is_directory = False

        return [Entry(f"{landing_path}/{n}", len(b)) for n, b in self.contents.items()]

    def download(self, path):
        import io

        class Response:
            def __init__(self, payload):
                self.contents = io.BytesIO(payload)

        return Response(self.contents[os.path.basename(path)])

    def upload(self, path, stream, overwrite=False):
        name = os.path.basename(path)
        if name in self.contents and not overwrite:
            raise AssertionError(f"would overwrite {name}")
        self.contents[name] = stream.read()
        self.uploads.append(name)

    # WorkspaceClient exposes these under .files
    @property
    def files(self):
        outer = self

        class Files:
            def list_directory_contents(self, p):
                return outer._list(p)

            def download(self, p):
                return outer.download(p)

            def upload(self, p, s, overwrite=False):
                return outer.upload(p, s, overwrite=overwrite)

            def create_directory(self, p):
                return None

        return Files()


def _run(tmp: str, landed: dict[str, bytes]) -> tuple[dict, FakeWorkspace]:
    fake = FakeWorkspace(landed)
    real_client = landing._client
    landing._client = lambda: fake
    try:
        return landing.land(tmp, "/Volumes/ow_tp/bronze/landing/custbill"), fake
    finally:
        landing._client = real_client


def test_same_name_same_length_different_bytes_is_a_conflict() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        corrected = b"C000000001ACME" + b" " * 36 + b"2026091500002000USD01\n"
        original = b"C000000001ACME" + b" " * 36 + b"2026091500001000USD01\n"
        pathlib.Path(tmp, "CUSTBILL_A.dat").write_bytes(corrected)
        try:
            _run(tmp, {"CUSTBILL_A.dat": original})
            check("in-place correction is a conflict", False, "landing did not raise")
        except SystemExit as exc:
            same_length = len(corrected) == len(original)
            check(
                "in-place correction is a conflict, not a skip",
                same_length and "digest" in str(exc),
                f"same_length={same_length} msg={exc}",
            )


def test_identical_rerun_is_a_skip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        payload = b"C000000001ACME" + b" " * 36 + b"2026091500001000USD01\n"
        pathlib.Path(tmp, "CUSTBILL_A.dat").write_bytes(payload)
        result, fake = _run(tmp, {"CUSTBILL_A.dat": payload})
        check(
            "byte-identical rerun skips and uploads nothing",
            [s["file"] for s in result["skipped"]] == ["CUSTBILL_A.dat"] and not fake.uploads,
            repr(result),
        )


def test_first_landing_uploads_and_records_the_digest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        payload = b"C000000001ACME" + b" " * 36 + b"2026091500001000USD01\n"
        pathlib.Path(tmp, "CUSTBILL_A.dat").write_bytes(payload)
        result, fake = _run(tmp, {})
        landed = result["landed"][0]
        check(
            "first landing uploads the bytes and records sha256",
            fake.contents["CUSTBILL_A.dat"] == payload
            and landed["sha256"] == hashlib.sha256(payload).hexdigest(),
            repr(result),
        )


def test_a_file_still_being_written_is_not_published() -> None:
    """The read sees a prefix; the re-stat sees the producer moved on."""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp, "CUSTBILL_A.dat")
        path.write_bytes(b"first half")

        real_open = builtins.open
        state = {"reads": 0}

        def growing_open(file, mode="r", *a, **kw):
            handle = real_open(file, mode, *a, **kw)
            if str(file) == str(path):
                state["reads"] += 1

                class Growing:
                    def __enter__(self_inner):
                        return self_inner

                    def __exit__(self_inner, *exc):
                        handle.close()
                        return False

                    def read(self_inner):
                        payload = handle.read()
                        # the producer appends while we are reading
                        with real_open(path, "ab") as producer:
                            producer.write(b" second half")
                        os.utime(path, ns=(0, state["reads"] * 1_000_000_000))
                        return payload

                return Growing()
            return handle

        landing.open = growing_open
        try:
            result, fake = _run(tmp, {})
        finally:
            landing.open = real_open
        check(
            "growing file is left for the next run, never published",
            [u["file"] for u in result["unstable"]] == ["CUSTBILL_A.dat"] and not fake.uploads,
            repr(result),
        )


def test_a_producer_that_pauses_over_the_window_is_not_published() -> None:
    """Nothing moves during the read itself; the growth lands inside the wait."""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp, "CUSTBILL_A.dat")
        path.write_bytes(b"first half")

        real_time = landing.time
        state = {"waits": 0}

        class PausingProducer:
            """A writer that is mid-burst: it appends whenever we wait on it."""

            def sleep(self, _seconds):
                state["waits"] += 1
                with open(path, "ab") as fh:
                    fh.write(b" more")
                os.utime(path, ns=(0, state["waits"] * 1_000_000_000))

        landing.time = PausingProducer()
        try:
            result, fake = _run(tmp, {})
        finally:
            landing.time = real_time
        check(
            "a producer pausing mid-burst never lands a prefix",
            [u["file"] for u in result["unstable"]] == ["CUSTBILL_A.dat"] and not fake.uploads,
            repr(result),
        )


if __name__ == "__main__":
    test_same_name_same_length_different_bytes_is_a_conflict()
    test_identical_rerun_is_a_skip()
    test_first_landing_uploads_and_records_the_digest()
    test_a_file_still_being_written_is_not_published()
    test_a_producer_that_pauses_over_the_window_is_not_published()
    print()
    if failures:
        print(f"{len(failures)} failure(s)")
        sys.exit(1)
    print("all landing checks passed")
