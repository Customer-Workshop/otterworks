"""Estate discovery: inventory, lineage, complexity, dead assets, DQ findings.

This is the pass that runs before any conversion, and its output is what the
fan-out is planned from -- so the numbers it reports are load-bearing. Two rules
follow from that:

* **Every finding is derived, never asserted.** Lineage comes from parsing the
  asset SQL; the dead-asset set comes from graph reachability against the job
  definitions that actually schedule work; the data-quality findings come from
  queries run against the live warehouse. Nothing in this file encodes "the
  answer" for the demo estate.
* **Unparseable is reported, not skipped.** An asset the parser cannot read is
  emitted with ``parse_status: "unparsed"`` and counted, because an inventory
  that silently omits the hard assets is exactly the inventory that makes a
  migration plan look finished when it is not.

Usage:
    python scan.py --estate ../legacy-estate --dsn "$DW_POSTGRES_DSN" \
        --out inventory.json --summary INVENTORY.md
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

SCHEMAS = ("staging", "core", "mart")
QUALIFIED = re.compile(
    r"\b(" + "|".join(SCHEMAS) + r")\.([a-z_][a-z0-9_]*)", re.IGNORECASE
)
WRITE_STATEMENT = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?"
    r"|TRUNCATE(?:\s+TABLE)?|MERGE\s+INTO)\s+([a-z_]+\.[a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)
INSERT_COLUMNS = re.compile(
    r"INSERT\s+INTO\s+[a-z_]+\.[a-z0-9_]+\s*\(([^)]*)\)", re.IGNORECASE
)
PROCEDURE_DECLARATION = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+"
    r"[a-z_]+\.[a-z_][a-z0-9_]*\s*\([^)]*\)",
    re.IGNORECASE,
)

# Assets that exist to *operate* the estate rather than to be migrated: the
# data generator, the schedule definitions, and the glue that invokes scripts.
# They are inventoried (a reader should see them) but excluded from the
# migratable count and the complexity ranking, because a fan-out sized off the
# seed file's complexity is sized off the wrong thing.
INFRASTRUCTURE_KINDS = frozenset({"seed", "jobs", "python"})

# Complexity weights. Deliberately crude and transparent: the score exists to
# rank assets for scheduling and to set reviewer expectations, so a reader must
# be able to reproduce it by eye from the counted features.
WEIGHTS = {
    "statements": 1.0,
    "source_tables": 2.0,
    "joins": 2.0,
    "ctes": 2.5,
    "window_functions": 4.0,
    "aggregates": 1.0,
    "subqueries": 3.0,
    "case_expressions": 0.5,
    "redshift_specific": 3.0,
    "procedural_blocks": 6.0,
    "lines": 0.05,
}
BANDS = ((12.0, "simple"), (35.0, "medium"))
REDSHIFT_CONSTRUCTS = (
    "getdate", "dateadd", "datediff", "listagg", "convert_timezone", "nvl",
    "distkey", "sortkey", "diststyle", "encode ", "trunc(",
)


@dataclass
class Asset:
    asset_id: str
    path: str
    kind: str
    writes: list[str] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)
    column_lineage: dict[str, list[str]] = field(default_factory=dict)
    features: dict[str, int] = field(default_factory=dict)
    complexity_score: float = 0.0
    complexity_band: str = "simple"
    redshift_constructs: list[str] = field(default_factory=list)
    scheduled: bool = False
    parse_status: str = "parsed"


def _count(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text, re.IGNORECASE))


def features_of(sql: str) -> tuple[dict[str, int], list[str]]:
    constructs = sorted({c.strip() for c in REDSHIFT_CONSTRUCTS if c in sql.lower()})
    features = {
        "statements": max(1, sql.count(";")),
        "joins": _count(r"\bjoin\b", sql),
        "ctes": _count(r"\bwith\b|\)\s*,\s*[a-z_]+\s+as\s*\(", sql),
        "window_functions": _count(r"\bover\s*\(", sql),
        "aggregates": _count(r"\b(sum|count|avg|min|max|string_agg|listagg)\s*\(", sql),
        "subqueries": max(0, _count(r"\(\s*select\b", sql)),
        "case_expressions": _count(r"\bcase\b", sql),
        "redshift_specific": len(constructs),
        "procedural_blocks": _count(r"\b(begin|loop|if\b.*then|exception)\b", sql),
        "lines": len(sql.splitlines()),
    }
    return features, constructs


def score(features: dict[str, int], source_tables: int) -> tuple[float, str]:
    total = WEIGHTS["source_tables"] * source_tables
    for key, weight in WEIGHTS.items():
        if key == "source_tables":
            continue
        total += weight * features.get(key, 0)
    total = round(total, 2)
    for threshold, band in BANDS:
        if total < threshold:
            return total, band
    return total, "complex"


def column_lineage(sql: str, reads: Iterable[str]) -> dict[str, list[str]]:
    """Map each written column to the source tables its expression can draw on.

    Column-level lineage from a regex is necessarily coarse: it resolves the
    target column list of an ``INSERT ... SELECT`` and attributes it to the
    tables the statement reads, which is honest about being statement-scoped
    rather than pretending to resolve each expression's exact provenance.
    """
    match = INSERT_COLUMNS.search(sql)
    if not match:
        return {}
    sources = sorted(set(reads))
    columns = [c.strip().strip('"') for c in match.group(1).split(",") if c.strip()]
    return {column: sources for column in columns}


def scan_asset(path: Path, estate: Path) -> Asset:
    text = path.read_text(errors="replace")
    parsed_text = PROCEDURE_DECLARATION.sub("", text)
    kind = path.parent.name if path.parent.parent.name == "ddl" else path.parent.name
    asset = Asset(
        asset_id=str(path.relative_to(estate)),
        path=str(path.relative_to(estate)),
        kind={"staging": "ddl", "core": "ddl", "mart": "ddl"}.get(kind, kind),
    )
    written = [m.group(1).lower() for m in WRITE_STATEMENT.finditer(parsed_text)]
    referenced = {
        f"{s.lower()}.{t.lower()}" for s, t in QUALIFIED.findall(parsed_text)
    }
    asset.writes = sorted(set(written))
    asset.reads = sorted(referenced - set(asset.writes))
    asset.features, asset.redshift_constructs = features_of(text)
    asset.complexity_score, asset.complexity_band = score(
        asset.features, len(asset.reads)
    )
    asset.column_lineage = column_lineage(text, asset.reads)
    # Only SQL is expected to name warehouse objects. A .sql file the parser
    # found nothing in is reported as unparsed rather than dropped, because an
    # inventory that silently omits what it could not read is the inventory that
    # makes a migration look smaller than it is.
    if path.suffix == ".sql" and not referenced:
        asset.parse_status = "unparsed"
    return asset


def scheduled_assets(estate: Path) -> set[str]:
    """Asset ids named by anything that actually schedules work."""
    named: set[str] = set()
    for path in sorted((estate / "jobs").rglob("*")):
        if path.is_file():
            text = path.read_text(errors="replace")
            named |= {m.group(0) for m in re.finditer(r"[\w/\-]+\.sql", text)}
            named |= {
                f"{s.lower()}.{t.lower()}" for s, t in QUALIFIED.findall(text)
            }
    return named


def dead_tables(assets: list[Asset], all_tables: set[str]) -> list[str]:
    """Tables no scheduled asset reads and no scheduled asset writes.

    Reachability, not a hardcoded list: a table is dead when nothing that the
    scheduler runs produces it *or* consumes it. A table written by a scheduled
    job is alive even if nothing reads it yet, and is reported separately as
    write-only rather than being called dead.
    """
    live_reads: set[str] = set()
    live_writes: set[str] = set()
    for asset in assets:
        if asset.scheduled:
            live_reads |= set(asset.reads)
            live_writes |= set(asset.writes)
    return sorted(all_tables - live_reads - live_writes)


def write_only_tables(assets: list[Asset]) -> list[str]:
    """Scheduled tables nothing downstream reads, excluding the mart layer.

    Mart tables are terminal by design -- their consumers are dashboards, not
    other assets -- so listing every mart here would bury the one signal that
    matters: an intermediate table being built for nobody.
    """
    reads: set[str] = set()
    writes: set[str] = set()
    for asset in assets:
        if asset.scheduled:
            reads |= set(asset.reads)
            writes |= set(asset.writes)
    return sorted(
        t for t in writes - reads if not t.startswith("mart.")
    )


DQ_PROBES: dict[str, str] = {
    # Duplicate business keys in the landing zone: the count of extra rows a
    # conversion must dedupe rather than trust.
    "duplicate_order_deliveries": """
        SELECT COUNT(*) - COUNT(DISTINCT order_id)
        FROM staging.stg_orders_raw
    """,
    # Categorical values whose spelling varies only by case: a conversion that
    # groups on the raw value silently splits every affected group.
    "case_variant_segments": """
        SELECT COUNT(*) FROM (
            SELECT UPPER(segment) AS normalised, COUNT(DISTINCT segment) AS spellings
            FROM staging.stg_customers_raw
            GROUP BY UPPER(segment)
            HAVING COUNT(DISTINCT segment) > 1
        ) AS variants
    """,
    # Events with no customer attribution: a join that is not an outer join
    # drops these rows entirely.
    "web_events_missing_customer": """
        SELECT COUNT(*) FROM staging.stg_web_events_raw WHERE customer_id IS NULL
    """,
    # Order items whose product no longer exists in the product feed.
    "order_items_orphan_product": """
        SELECT COUNT(*)
        FROM staging.stg_order_items_raw i
        LEFT JOIN staging.stg_products_raw p ON p.product_id = i.product_id
        WHERE p.product_id IS NULL
    """,
}


def run_dq_probes(dsn: str) -> dict[str, int]:
    import psycopg2  # imported here so a code-only scan needs no database

    findings: dict[str, int] = {}
    with psycopg2.connect(dsn) as connection:
        with connection.cursor() as cursor:
            for name, sql in DQ_PROBES.items():
                cursor.execute(sql)
                row = cursor.fetchone()
                findings[name] = int(row[0]) if row and row[0] is not None else 0
    return findings


def catalog_tables(dsn: str) -> dict[str, int]:
    import psycopg2
    from psycopg2 import sql

    with psycopg2.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_schema || '.' || table_name
                FROM information_schema.tables
                WHERE table_schema = ANY(%s) AND table_type = 'BASE TABLE'
                ORDER BY 1
                """,
                (list(SCHEMAS),),
            )
            names = [row[0] for row in cursor.fetchall()]
            counts: dict[str, int] = {}
            for name in names:
                schema, table = name.split(".", 1)
                cursor.execute(  # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                    sql.SQL("SELECT COUNT(*) FROM {}").format(
                        sql.Identifier(schema, table)
                    )
                )
                counts[name] = int(cursor.fetchone()[0])
    return counts


def summarise(inventory: dict) -> str:
    bands = inventory["totals"]["by_band"]
    lines = [
        "# Legacy warehouse inventory",
        "",
        f"- assets discovered: **{inventory['totals']['assets']}**"
        f" ({', '.join(f'{k}: {v}' for k, v in inventory['totals']['by_kind'].items())})",
        f"- of those, migratable: **{inventory['totals']['migratable']}**"
        " (the rest operate the estate: seed, schedules, glue)",
        f"- scheduled by a job definition: **{inventory['totals']['scheduled']}**",
        f"- unparsed (reported, not skipped): **{inventory['totals']['unparsed']}**",
        f"- tables in the catalog: **{inventory['totals']['tables']}**"
        f" holding {inventory['totals']['rows']:,} rows",
        f"- complexity: {bands.get('simple', 0)} simple,"
        f" {bands.get('medium', 0)} medium, {bands.get('complex', 0)} complex",
        "",
        "## Not worth migrating",
        "",
    ]
    for table in inventory["dead_tables"]:
        rows = inventory["catalog"].get(table, 0)
        lines.append(f"- `{table}` — unreachable from any scheduled job ({rows:,} rows)")
    if inventory["write_only_tables"]:
        lines.append("")
        lines.append("Written but never read (candidates, not conclusions):")
        lines += [f"- `{t}`" for t in inventory["write_only_tables"]]
    lines += ["", "## Data-quality findings", ""]
    for name, value in inventory["data_quality"].items():
        lines.append(f"- `{name}`: **{value:,}**")
    lines += ["", "## Heaviest migratable assets", ""]
    heaviest = [
        a for a in inventory["assets"]
        if a["asset_id"] in set(inventory["migratable_asset_ids"])
    ]
    for asset in heaviest[:8]:
        lines.append(
            f"- `{asset['path']}` — {asset['complexity_band']}"
            f" (score {asset['complexity_score']},"
            f" {len(asset['reads'])} sources,"
            f" constructs: {', '.join(asset['redshift_constructs']) or 'none'})"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--estate", type=Path, required=True)
    parser.add_argument("--dsn", help="Postgres DSN; omit for a code-only scan")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args(argv)

    paths = [
        p
        for p in sorted(args.estate.rglob("*"))
        if p.is_file() and p.suffix in {".sql", ".py"} and "compat" not in p.parts
    ]
    assets = [scan_asset(p, args.estate) for p in paths]
    named = scheduled_assets(args.estate)
    for asset in assets:
        asset.scheduled = asset.path in named or any(
            Path(asset.path).name in n for n in named
        ) or bool(set(asset.writes) & named)

    catalog = catalog_tables(args.dsn) if args.dsn else {}
    quality = run_dq_probes(args.dsn) if args.dsn else {}
    tables = set(catalog) | {t for a in assets for t in a.writes + a.reads}

    assets.sort(key=lambda a: a.complexity_score, reverse=True)
    migratable = [a for a in assets if a.kind not in INFRASTRUCTURE_KINDS]
    by_kind: dict[str, int] = {}
    by_band: dict[str, int] = {}
    for asset in assets:
        by_kind[asset.kind] = by_kind.get(asset.kind, 0) + 1
    for asset in migratable:
        by_band[asset.complexity_band] = by_band.get(asset.complexity_band, 0) + 1

    inventory = {
        "estate": str(args.estate),
        "totals": {
            "assets": len(assets),
            "migratable": len(migratable),
            "scheduled": sum(1 for a in assets if a.scheduled),
            "unparsed": sum(1 for a in assets if a.parse_status == "unparsed"),
            "tables": len(catalog) or len(tables),
            "rows": sum(catalog.values()),
            "by_kind": by_kind,
            "by_band": by_band,
        },
        "catalog": catalog,
        "dead_tables": dead_tables(assets, set(catalog) or tables),
        "write_only_tables": write_only_tables(assets),
        "data_quality": quality,
        "assets": [asdict(a) for a in assets],
        "migratable_asset_ids": [a.asset_id for a in migratable],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    if args.summary:
        args.summary.write_text(summarise(inventory))
    print(
        f"{inventory['totals']['assets']} assets, "
        f"{inventory['totals']['tables']} tables, "
        f"{len(inventory['dead_tables'])} dead, "
        f"{inventory['totals']['unparsed']} unparsed -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
