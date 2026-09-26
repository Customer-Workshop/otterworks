"""Wave 1 / batch w1-b01 loader: OW_BILLING CUSTOMER_MASTER (+ ENTITY_ATTR_VALUE
embedded as attributes[] keyed by ENTITY_ID -- mapping v1.1.0 embeds it unscoped
because the census shows every row is ENTITY_TYPE='CUSTOMER'; element key eavId,
never collapsed to a map: (ENTITY_ID, ATTR_NAME) repeats) -> mmp_rt_billing.customers.

Idempotent: the single declared write target is dropped and recreated per run
(playbook 3 step 4), then written by replace-upsert on _id via the shared wave-0
helpers (common.load_unit). Orphan attribute rows (no CUSTOMER_MASTER parent) are
counted and reported, never written. Mapping: .migration/mapping/customers.json v1.1.0.
Usage: ~/.venvs/recon/bin/python services/legacy-billing/migration/load_customers.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_mapping, load_unit, mongo_db, oracle_connect  # noqa: E402

MAPPING = ".migration/mapping/customers.json"
WRITE_TARGETS = ("customers",)


def main():
    mapping = load_mapping(MAPPING)
    db = mongo_db()
    with oracle_connect() as conn:
        for name, (n, orphans) in load_unit(conn, db, mapping, WRITE_TARGETS).items():
            extra = f" ({orphans} orphan child rows skipped)" if orphans else ""
            print(f"loaded mmp_rt_billing.{name}: {n} docs{extra}")


if __name__ == "__main__":
    main()
