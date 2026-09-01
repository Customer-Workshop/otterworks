#!/usr/bin/env python3
"""Create a verbatim unit subset because the approved spec is one flat 16-collection document and the harness reconciles every collection in the file it is given (--unit is only a label).

Two key expressions are re-rendered for the harness (fields are always verbatim); every
rendering is asserted against the approved entry and recorded in the emitted file under
`_recon_key_rendering`.

Approved embed exclusions are explicit and recorded in the emitted subset; all remaining
embeds are asserted verbatim against the approved mapping.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1].parent

# The harness keys a source row by the cursor-description name of each key expression
# (adapters._SqlAdapterBase.fetch_keyed), so a key expression only round-trips when Oracle
# reports it back character-for-character.
KEY_RENDERING = {
    "codes": {
        "source": ["CODE_TYPE||'#'||CODE_VAL"],
        "kind": "whitespace_only",
        "reason": (
            "Oracle strips whitespace from cursor-description names, so the approved "
            "expression only round-trips written without spaces. Whitespace-only rewrite: "
            "same expression, same composed value."
        ),
    },
    "fixture_meta": {
        "source": [
            "INITIALIZED_AT-NUMTODSINTERVAL("
            "MOD(TO_NUMBER(TO_CHAR(INITIALIZED_AT,'FF6')),1000)/1000000,'SECOND')"
        ],
        "kind": "canonicalization_applied_source_side",
        "reason": (
            "The harness keys pre-canonicalization, and TIMESTAMP(6) cannot round-trip "
            "through a millisecond BSON date. This applies canonicalization v1.0 rule "
            "datetime_utc_truncate_ms (DATE,TIMESTAMP*->date) to the approved key column "
            "INITIALIZED_AT on the source side; no other column is referenced."
        ),
    },
}
EMBED_EXCLUSION_REASONS = {
    ("invoices", "dunning_attempts"): "U6-owned, sequential batch, deferred",
}


def _render_key(entry: dict) -> dict | None:
    """Apply the declared rendering to one approved entry, asserting equivalence."""
    rendering = KEY_RENDERING.get(entry["collection"])
    if rendering is None:
        return None
    approved = entry["key"]["source"]
    rendered = rendering["source"]
    if len(approved) != len(rendered):
        raise AssertionError(f"{entry['collection']}: rendered key arity differs from the approved key")
    for approved_expr, rendered_expr in zip(approved, rendered):
        if rendering["kind"] == "whitespace_only":
            if "".join(approved_expr.split()) != "".join(rendered_expr.split()):
                raise AssertionError(
                    f"{entry['collection']}: rendered key is not a whitespace-only rewrite "
                    f"of the approved key"
                )
        elif rendering["kind"] == "canonicalization_applied_source_side":
            if approved_expr not in rendered_expr:
                raise AssertionError(
                    f"{entry['collection']}: rendered key does not reference the approved "
                    f"key column {approved_expr}"
                )
        else:
            raise AssertionError(f"{entry['collection']}: unknown key rendering kind")
    entry["key"] = {"source": list(rendered), "target": entry["key"]["target"]}
    return {
        "approved_key_source": list(approved),
        "rendered_key_source": list(rendered),
        "kind": rendering["kind"],
        "reason": rendering["reason"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spec",
        default=REPO_ROOT / ".migration/03_mapping_spec.json",
        type=Path,
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--collection", action="append", required=True)
    parser.add_argument(
        "--exclude-embed",
        action="append",
        default=[],
        metavar="COLLECTION.ARRAY_PATH",
        help="exclude an approved embedded array from reconciliation (repeatable)",
    )
    args = parser.parse_args()

    source = json.loads(args.spec.read_text())
    source_entries = source.get("collections", [])
    by_name = {entry["collection"]: entry for entry in source_entries}
    missing = [name for name in args.collection if name not in by_name]
    if missing:
        raise SystemExit(
            f"requested collection(s) absent from {args.spec}: {', '.join(missing)}"
        )
    requested = set(args.collection)
    exclusions = []
    exclusions_by_collection = {}
    for raw in args.exclude_embed:
        try:
            collection, array_path = raw.split(".", 1)
        except ValueError as exc:
            raise SystemExit(
                f"--exclude-embed must be COLLECTION.ARRAY_PATH: {raw}"
            ) from exc
        reason = EMBED_EXCLUSION_REASONS.get((collection, array_path))
        if reason is None:
            raise SystemExit(f"no approved exclusion reason for {raw}")
        if collection not in requested:
            raise SystemExit(f"excluded embed collection is not selected: {raw}")
        if (collection, array_path) in exclusions_by_collection.get(collection, set()):
            raise SystemExit(f"duplicate --exclude-embed: {raw}")
        exclusions_by_collection.setdefault(collection, set()).add((collection, array_path))
        exclusions.append(
            {"collection": collection, "array_path": array_path, "reason": reason}
        )
    selected = [
        copy.deepcopy(entry)
        for entry in source_entries
        if entry["collection"] in requested
    ]
    for entry in selected:
        approved = by_name[entry["collection"]]
        rendering = _render_key(entry)
        if rendering is not None:
            entry["_recon_key_rendering"] = rendering
        else:
            entry_key = entry["key"]
            if entry_key != approved["key"]:
                raise AssertionError(f"{entry['collection']}: key altered without a declared rendering")
        if entry.get("fields") != approved.get("fields"):
            raise AssertionError(f"{entry['collection']}: fields differ from the approved entry")
        if entry["root_table"] != approved["root_table"] or entry.get("root_where") != approved.get("root_where"):
            raise AssertionError(f"{entry['collection']}: root scope differs from the approved entry")
        approved_embeds = approved.get("embeds", [])
        excluded_paths = {
            item["array_path"]
            for item in exclusions
            if item["collection"] == entry["collection"]
        }
        embeds = entry.get("embeds", [])
        for array_path in excluded_paths:
            matches = [embed for embed in approved_embeds if embed["array_path"] == array_path]
            if len(matches) != 1:
                raise AssertionError(
                    f"{entry['collection']}.{array_path}: excluded embed is not approved"
                )
        if approved_embeds or excluded_paths:
            entry["embeds"] = [
                embed
                for embed in embeds
                if embed["array_path"] not in excluded_paths
            ]
        expected_embeds = [
            embed for embed in approved_embeds if embed["array_path"] not in excluded_paths
        ]
        if entry.get("embeds", []) != expected_embeds:
            raise AssertionError(
                f"{entry['collection']}: non-excluded embeds differ from approved entry"
            )

    payload = {
        "version": source["version"],
        "collections": selected,
        "_recon_embed_exclusions": exclusions,
    }
    encoded = json.dumps(payload, indent=2) + "\n"
    if json.loads(encoded)["collections"] != selected:
        raise AssertionError("serialized unit mapping changed an entry")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(encoded)
    return 0


if __name__ == "__main__":
    main()
