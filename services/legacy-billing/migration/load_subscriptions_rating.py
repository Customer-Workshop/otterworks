"""Wave 1 / batch w1-b03 loader, unit subscriptions_rating:
OW_BILLING SUBSCRIPTIONS, USAGE_EVENTS, RATING_PERIODS(+RATING_RESULTS embedded as results[]) -> mmp_rt_billing.{subscriptions,usage_events,rating_periods}.

Idempotent: each declared write target is dropped and recreated per run (playbook 3 step 4),
then written by replace-upsert on _id. Embedded child rows whose parent is missing are counted
and reported, never written. Reads the source with one connection (source_concurrency 1).
Usage: ~/.venvs/recon/bin/python services/legacy-billing/migration/load_subscriptions_rating.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_mapping, load_unit, mongo_db, oracle_connect  # noqa: E402

MAPPING = ".migration/mapping/subscriptions_rating.json"
WRITE_TARGETS = ("subscriptions", "usage_events", "rating_periods")


def main():
    mapping = load_mapping(MAPPING)
    db = mongo_db()
    with oracle_connect() as conn:
        for name, (n, orphans) in load_unit(conn, db, mapping, WRITE_TARGETS).items():
            extra = f" ({orphans} orphan child rows skipped)" if orphans else ""
            print(f"loaded mmp_rt_billing.{name}: {n} docs{extra}")


if __name__ == "__main__":
    main()
