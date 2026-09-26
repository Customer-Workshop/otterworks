"""Wave 0 / batch w0-b01 loader: OW_BILLING CODES, TENANTS, PLANS -> mmp_rt_billing.{codes,tenants,plans}.

Idempotent: each declared write target is dropped and recreated per run (playbook 3 step 4).
Usage: ~/.venvs/recon/bin/python services/legacy-billing/migration/load_shared_reference.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_collection, load_mapping, mongo_db, oracle_connect  # noqa: E402

MAPPING = ".migration/mapping/shared-reference.json"
WRITE_TARGETS = ("codes", "tenants", "plans")


def main():
    mapping = load_mapping(MAPPING)
    db = mongo_db()
    with oracle_connect() as conn:
        for name in WRITE_TARGETS:
            n = load_collection(conn, db, mapping, name)
            print(f"loaded mmp_rt_billing.{name}: {n} docs")


if __name__ == "__main__":
    main()
