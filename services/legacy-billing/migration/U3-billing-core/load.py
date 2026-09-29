"""U3-billing-core fixture/live loader: the OW_BILLING billing core -> 10 collections.

subscriptions, subscriptions_hist, usage_events, rating_periods, rating_results,
billing_invoices (INVOICES + embedded INVOICE_LINES), credit_notes,
dunning_attempts, notifications, billing_audit_log. One document per root row.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".migration" / "tools"))
import mongo_load

UNIT = "U3-billing-core"


def _load_collection(spec, db, allowed, stats, name, rows, embeds=None):
    coll = mongo_load.coll_spec(spec, name)
    docs = mongo_load.build_root_docs(coll, rows, embeds)
    stats["doc_counts"][name] = len(docs)
    stats["bulk"][name] = mongo_load.write_collection(
        db, name, docs, coll.get("indexes"), allowed
    )


def load(cur, db, allowed):
    spec = mongo_load.load_spec()
    stats = {"source_counts": {}, "doc_counts": {}, "bulk": {}}

    cur.execute("SELECT * FROM ow_billing.subscriptions")
    rows = mongo_load.fetch_dicts(cur)
    stats["source_counts"]["subscriptions"] = len(rows)
    _load_collection(spec, db, allowed, stats, "subscriptions", rows)

    cur.execute("SELECT * FROM ow_billing.subscriptions_hist")
    rows = mongo_load.fetch_dicts(cur)
    stats["source_counts"]["subscriptions_hist"] = len(rows)
    _load_collection(spec, db, allowed, stats, "subscriptions_hist", rows)

    cur.execute("SELECT * FROM ow_billing.usage_events")
    rows = mongo_load.fetch_dicts(cur)
    stats["source_counts"]["usage_events"] = len(rows)
    _load_collection(spec, db, allowed, stats, "usage_events", rows)

    cur.execute("SELECT * FROM ow_billing.rating_periods")
    rows = mongo_load.fetch_dicts(cur)
    stats["source_counts"]["rating_periods"] = len(rows)
    _load_collection(spec, db, allowed, stats, "rating_periods", rows)

    cur.execute("SELECT * FROM ow_billing.rating_results")
    rows = mongo_load.fetch_dicts(cur)
    stats["source_counts"]["rating_results"] = len(rows)
    _load_collection(spec, db, allowed, stats, "rating_results", rows)

    cur.execute("SELECT * FROM ow_billing.invoices")
    invoices = mongo_load.fetch_dicts(cur)
    cur.execute("SELECT * FROM ow_billing.invoice_lines")
    lines = mongo_load.fetch_dicts(cur)
    stats["source_counts"]["invoices"] = len(invoices)
    stats["source_counts"]["invoice_lines"] = len(lines)
    _load_collection(
        spec, db, allowed, stats, "billing_invoices", invoices, {"lines": lines}
    )

    cur.execute("SELECT * FROM ow_billing.credit_notes")
    rows = mongo_load.fetch_dicts(cur)
    stats["source_counts"]["credit_notes"] = len(rows)
    _load_collection(spec, db, allowed, stats, "credit_notes", rows)

    cur.execute("SELECT * FROM ow_billing.dunning_attempts")
    rows = mongo_load.fetch_dicts(cur)
    stats["source_counts"]["dunning_attempts"] = len(rows)
    _load_collection(spec, db, allowed, stats, "dunning_attempts", rows)

    cur.execute("SELECT * FROM ow_billing.notifications")
    rows = mongo_load.fetch_dicts(cur)
    stats["source_counts"]["notifications"] = len(rows)
    _load_collection(spec, db, allowed, stats, "notifications", rows)

    cur.execute("SELECT * FROM ow_billing.billing_audit_log")
    rows = mongo_load.fetch_dicts(cur)
    stats["source_counts"]["billing_audit_log"] = len(rows)
    _load_collection(spec, db, allowed, stats, "billing_audit_log", rows)

    return stats


if __name__ == "__main__":
    mongo_load.run_unit(UNIT, load)
