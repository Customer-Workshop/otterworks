from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from client import require_custbill_ns
from custbill import bronze_rows_from_file, legacy_dat_files, silver_rows_from_file
from recon_custbill import REQUIRED, content_fingerprint, idempotency_result, verdict


@pytest.fixture(scope="session")
def generated_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("custbill-legacy")
    env = os.environ.copy()
    env["OTTERWORKS_LEGACY_ROOT"] = str(root)
    subprocess.run(
        ["make", "legacy-etl-gen-data", "NS=w0test"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    source = root / "sftp-drop" / "upload" / "CUSTBILL_W0TEST_001.dat"
    shutil.copyfile(source, root / "bronze_source.dat")
    env["RUN_ALL_SLEEP"] = "0"
    subprocess.run(
        ["make", "legacy-etl-run", "JOB=run_all"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return root


def test_bronze_rows_from_generated_dat(generated_root: Path) -> None:
    files = legacy_dat_files(generated_root)
    assert files[0][0].endswith(".dat")
    assert files[0][1].name.endswith(".dat.done")
    rows = bronze_rows_from_file(files[0][1], files[0][0])
    assert rows
    assert rows[0]["record_kind"] == "HDR"
    assert rows[-1]["record_kind"] == "TRL"
    assert all(row["source_file"] == files[0][0] for row in rows)
    assert [row["line_no"] for row in rows] == list(range(1, len(rows) + 1))
    assert len({row["file_sha256"] for row in rows}) == 1


def test_bronze_rows_preserve_latin1_and_newline_only(tmp_path: Path) -> None:
    source = tmp_path / "CUSTBILL_BYTE.dat.done"
    source.write_bytes(b"HDR header\r\ncaf\xe9\x0bbody\n")
    rows = bronze_rows_from_file(source, "CUSTBILL_BYTE.dat")
    assert rows[1]["raw_line"] == "caf\xe9\x0bbody"
    assert rows[1]["raw_line"].encode("latin-1") == b"caf\xe9\x0bbody"


def test_silver_rows_from_generated_psv(generated_root: Path) -> None:
    parsed = generated_root / "parsed" / "CUSTBILL_W0TEST_001.psv"
    rows = silver_rows_from_file(parsed)
    assert rows
    assert rows[0]["source_file"] == "CUSTBILL_W0TEST_001.dat"
    assert rows[0]["line_no"] == 1
    assert set(rows[0]) == {
        "source_file", "line_no", "cust_id", "cust_name", "bill_date",
        "bill_amt", "currency", "rec_type",
    }


@pytest.mark.parametrize("ns", [
    "demo", "sftp-ingest-poll-w1", "parse-w2", "parse-w2-anom",
    "finance-w2", "custbill-workflow-w3",
])
def test_custbill_namespaces_accept_registered_values(ns: str) -> None:
    assert require_custbill_ns(ns) == ns


@pytest.mark.parametrize("ns", ["Parse_W2", "-x", "a" * 33, "x;drop"])
def test_custbill_namespaces_reject_invalid_values(ns: str) -> None:
    with pytest.raises(SystemExit, match=r"namespace must match"):
        require_custbill_ns(ns)


def test_content_fingerprint_distinguishes_row_fields() -> None:
    assert content_fingerprint(["a|1", "b|2"]) != content_fingerprint(["a|1", "b|3"])


def _checks_with_skipped(unit: str, skipped_id: str) -> list[dict]:
    return [
        {"id": check_id, "result": "skipped" if check_id == skipped_id else "pass"}
        for check_id in REQUIRED[unit]
    ]


def test_verdict_parse_skipped_required_is_red_unless_waived() -> None:
    checks = _checks_with_skipped("parse_custbill_fixedwidth", "U7-e")
    assert verdict("parse_custbill_fixedwidth", checks, None, set()) == ["U7-e (skipped, not waived)"]
    assert verdict("parse_custbill_fixedwidth", checks, None, {"U7-e"}) == []


def test_verdict_finance_openpyxl_skip_is_red() -> None:
    checks = _checks_with_skipped("finance_excel_report", "U8-e")
    assert verdict("finance_excel_report", checks, None, set()) == ["U8-e (skipped, not waived)"]


def test_verdict_workflow_run_state_skip_is_red() -> None:
    checks = _checks_with_skipped("custbill_workflow", "U9-c")
    assert verdict("custbill_workflow", checks, None, set()) == ["U9-c (skipped, not waived)"]


def test_idempotency_same_run_is_fail() -> None:
    run = {"run_id": 1, "end_time": 100, "result_state": "SUCCESS"}
    result, reason = idempotency_result(True, True, run, run, 50)
    assert result == "fail"
    assert "newer" in reason


def test_idempotency_newer_successful_run_is_pass() -> None:
    previous = {"run_id": 1, "end_time": 100, "result_state": "SUCCESS"}
    current = {"run_id": 2, "end_time": 200, "result_state": "SUCCESS"}
    assert idempotency_result(True, True, previous, current, 150) == (
        "pass", "newer successful ow_tp_custbill run confirmed"
    )


def test_idempotency_newer_run_with_changed_fingerprint_is_fail() -> None:
    previous = {"run_id": 1, "end_time": 100, "result_state": "SUCCESS"}
    current = {"run_id": 2, "end_time": 200, "result_state": "SUCCESS"}
    result, reason = idempotency_result(False, True, previous, current, 150)
    assert result == "fail"
    assert reason == "fingerprints differ"


def test_idempotency_without_runs_is_fail() -> None:
    result, reason = idempotency_result(True, True, None, None, 100)
    assert result == "fail"
    assert "no newer successful" in reason


def test_idempotency_run_ending_before_snapshot_is_fail() -> None:
    current = {"run_id": 2, "end_time": 100, "result_state": "SUCCESS"}
    result, reason = idempotency_result(True, True, None, current, 200)
    assert result == "fail"
    assert reason == "latest successful run ended before the first-pass snapshot"


def test_idempotency_run_ending_after_snapshot_is_pass() -> None:
    current = {"run_id": 2, "end_time": 300, "result_state": "SUCCESS"}
    assert idempotency_result(True, True, None, current, 200) == (
        "pass", "newer successful ow_tp_custbill run confirmed"
    )


def test_legacy_dat_files_history_reads_year_dirs(tmp_path: Path) -> None:
    hist = tmp_path / "sftp-drop" / "history" / "2023"
    hist.mkdir(parents=True)
    (hist / "CUSTBILL_X_202301.dat").write_bytes(b"HDR\nTRL\n")
    (tmp_path / "incoming").mkdir()
    (tmp_path / "incoming" / "CUSTBILL_X_001.dat").write_bytes(b"HDR\nTRL\n")
    assert [name for name, _ in legacy_dat_files(tmp_path)] == ["CUSTBILL_X_001.dat"]
    assert [name for name, _ in legacy_dat_files(tmp_path, history=True)] == ["CUSTBILL_X_202301.dat"]


def test_delete_tree_drains_paged_listings() -> None:
    from custbill import _delete_tree

    class FakeDbx:
        def __init__(self) -> None:
            self.files = {f"/v/a/f{i}": None for i in range(5)} | {"/v/a/sub/g": None}
            self.deleted_dirs: list[str] = []

        def list_dir(self, path: str) -> list[dict]:
            prefix = path.rstrip("/") + "/"
            names = sorted({p[len(prefix):].split("/")[0] for p in self.files if p.startswith(prefix)})
            page = [{"path": prefix + n, "name": n, "is_directory": (prefix + n + "/") in {p[:len(prefix + n) + 1] for p in self.files}}
                    for n in names[:2]]
            return page

        def delete_file(self, path: str) -> int:
            del self.files[path]
            return 204

        def delete_dir(self, path: str) -> int:
            self.deleted_dirs.append(path)
            return 204

    dbx = FakeDbx()
    _delete_tree(dbx, "/v/a")
    assert dbx.files == {}
    assert dbx.deleted_dirs[-1] == "/v/a" and "/v/a/sub" in dbx.deleted_dirs
