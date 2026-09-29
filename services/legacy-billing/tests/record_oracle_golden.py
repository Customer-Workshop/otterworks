"""Record the Oracle side of the Mongo parity suite.

Run against a freshly seeded *scratch* Oracle fixture (the write cases mutate it):

    ORACLE_PORT=52522 USAGE_INTERNAL_TOKEN=parity-internal-token BILLING_BACKEND=oracle \
        python tests/record_oracle_golden.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import parity_cases
from app import app


def main():
    if os.getenv("BILLING_BACKEND") != "oracle":
        raise SystemExit("BILLING_BACKEND=oracle is required to record the Oracle golden")
    if os.getenv("USAGE_INTERNAL_TOKEN") != parity_cases.INTERNAL_TOKEN:
        raise SystemExit(f"USAGE_INTERNAL_TOKEN={parity_cases.INTERNAL_TOKEN} is required")
    golden = parity_cases.record(app.test_client())
    failed = sorted(name for group in golden.values() for name, result in group.items() if result["status"] >= 500)
    if failed:
        raise SystemExit(f"Oracle fixture returned 5xx for {failed}; reseed the scratch fixture and re-record")
    parity_cases.write_golden(golden)
    print(f"wrote {parity_cases.GOLDEN_PATH}")


if __name__ == "__main__":
    main()
