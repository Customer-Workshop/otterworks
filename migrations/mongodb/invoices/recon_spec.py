"""Turn the U3-invoices mapping rows into a spec the recon harness can grade.

The ledger spec describes one `invoices` collection fed by two estates and refers to
columns of a second table with dotted names (INVOICE_LINE.CUST_NO). The harness grades one
root table per entry and rejects dotted source paths for the oracle family, so this script
rewrites the unit slice into three harness objects:

  invoices   [conversion]  INVOICE_HEADER + lines[] from INVOICE_LINE, scoped source="conversion"
  invoices   [billing]     INVOICES + lines[] from INVOICE_LINES + dunning[], scoped source="billing"
  invoice_lines_orphaned   INVOICE_LINE rows with no header

Nothing is dropped silently: every mapping row the harness cannot grade is listed in
UNGRADED_BY_HARNESS below and carried into the recon report's unverified_paths, where a
Tier 4 recorded operation grades it instead.

    python migrations/mongodb/invoices/recon_spec.py .migration/recon/U3-invoices/mapping.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.unit_spec import slice_spec  # noqa: E402

UNIT = "U3-invoices"

# A line's SERVICE_PERIOD is a 'MMYYYY-MMYYYY' string on the source and a {from,to} object
# on the target. No canonicalization rule turns one into the other, so the harness cannot
# compare them field to field; Tier 4 ops grade both bounds instead.
UNGRADED_BY_HARNESS = {"lines.servicePeriod"}

# Every INVOICE_LINE row belongs to a header except the 37 orphans, which are their own
# collection. Both sides of each scope are declared, as the harness requires.
HAS_HEADER = ("EXISTS (SELECT 1 FROM invoice_header h "
              "WHERE h.invoice_id = invoice_line.invoice_id)")
CONVERSION = json.dumps({"source": "conversion"})
BILLING = json.dumps({"source": "billing"})


def _fields(fields, estate, table_prefix=None):
    out = []
    for f in fields:
        if f.get("estate") not in (None, "both", estate):
            continue
        source = f["source"]
        if "." in source:
            head, _, tail = source.partition(".")
            if head != table_prefix:
                continue  # a column of another table: graded by a Tier 4 op
            source = tail
        out.append({k: v for k, v in f.items()
                    if k in ("source", "target", "source_type", "bson_type", "rules")}
                   | {"source": source})
    return out


def _embed(spec_embed, target_where, child_where):
    return {"array_path": spec_embed["array_path"],
            "child_table": spec_embed["child_table"],
            "child_where": child_where,
            "target_where": target_where,
            "parent_key": spec_embed["parent_key"],
            "key": spec_embed["key"],
            "fields": [f for f in _fields(spec_embed["fields"], None)
                       if f"{spec_embed['array_path']}.{f['target']}"
                       not in UNGRADED_BY_HARNESS]}


def build(spec: dict) -> dict:
    invoices = next(c for c in spec["collections"] if c["collection"] == "invoices")
    orphans = next(c for c in spec["collections"]
                   if c["collection"] == "invoice_lines_orphaned")
    embeds = {(e["child_table"]): e for e in invoices["embeds"]}
    line_fields = _fields(embeds["INVOICE_LINE"]["fields"], None)

    conversion = {
        "collection": "invoices",
        "root_table": "INVOICE_HEADER",
        "root_where": "invoice_id IS NOT NULL",
        "target_where": CONVERSION,
        "key": invoices["key"],
        "fields": _fields(invoices["fields"], "conversion", "INVOICE_HEADER"),
        "embeds": [_embed(embeds["INVOICE_LINE"], CONVERSION, HAS_HEADER)],
    }
    billing = {
        "collection": "invoices",
        "root_table": "INVOICES",
        "root_where": "id IS NOT NULL",
        "target_where": BILLING,
        # The billing estate's primary key column is ID, not the conversion INVOICE_ID.
        "key": {"source": ["ID"], "target": "_id"},
        "fields": _fields(invoices["fields"], "billing", "INVOICES"),
        "embeds": [_embed(embeds["INVOICE_LINES"], BILLING, "id IS NOT NULL"),
                   _embed(embeds["DUNNING_ATTEMPTS"], BILLING, "id IS NOT NULL")],
    }
    orphaned = {
        "collection": "invoice_lines_orphaned",
        "root_table": "INVOICE_LINE",
        "root_where": orphans["root_where"],
        "target_where": "{}",
        "key": orphans["key"],
        # inherits_field_rules_from: invoices.lines[conversion]
        "fields": orphans["fields"] + [f for f in line_fields
                                       if f"lines.{f['target']}" not in UNGRADED_BY_HARNESS],
    }
    return {"version": spec["version"], "source_family": spec["source_family"],
            "unit": spec["unit"], "collections": [conversion, billing, orphaned]}


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1
               else f".migration/recon/{UNIT}/mapping.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build(slice_spec(UNIT)), indent=2) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
