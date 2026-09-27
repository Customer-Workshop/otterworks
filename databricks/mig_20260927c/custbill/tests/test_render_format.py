"""Pure-python parity test: render_custbill.format_record must equal the legacy
oracle_custbill_extract.format_record byte-for-byte.
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


legacy = _load(REPO / "etl/legacy-extra/tools/oracle_custbill_extract.py", "legacy_custbill")
converted = _load(REPO / "databricks/mig_20260927c/custbill/src/render_custbill.py",
                  "render_custbill")


ROWS = [
    {"invoice_id": "i1", "cust_no": "C00001", "cust_name": "Acme Corp",
     "period_end": "2026-01-31", "total_amt": "1234.56", "record_type": "01"},
    {"invoice_id": "i2", "cust_no": "C00002", "cust_name": "Crédit Mémoire Ünïcode",
     "period_end": "2026-02-28", "total_amt": "-99.99", "record_type": "02"},
    {"invoice_id": "i3", "cust_no": "LONGCUSTNUMBER999", "cust_name": "A very long "
     "customer name that exceeds thirty characters", "period_end": "2025-12-01",
     "total_amt": "0.005", "record_type": "01"},
]


def test_format_record_matches_legacy():
    for row in ROWS:
        assert converted.format_record(dict(row)) == legacy.format_record(dict(row))


def test_record_length_65():
    for row in ROWS:
        assert len(converted.format_record(dict(row))) == 65


def test_file_bytes_trailing_newline():
    payload = converted.build_file_bytes(ROWS[:2])
    assert payload.endswith(b"\n")
    assert payload.count(b"\n") == 2
