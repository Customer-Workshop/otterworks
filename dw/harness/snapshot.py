"""Write one deterministic manifest for each requested warehouse table."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from assets import fingerprint_for
from manifest import build
from ordering import has_top_level_comma
from sources import DuckDBSource, PostgresSource, Source


# Add ordered assets here when sequence is part of their business contract.
# Values are individual SQL expressions, not user-supplied shell text.
ORDERED_KEYS: dict[str, tuple[str, ...]] = {
    "core.dim_customer_scd2": ("customer_id", "effective_from", "customer_sk"),
}


def _postgres_dsn() -> str:
    return os.environ.get(
        "DW_POSTGRES_DSN",
        "host=127.0.0.1 port=15432 dbname=analytics_dw "
        "user=dw_admin password=dw_local_dev sslmode=disable",
    )


def _manifest_path(out: Path, table: str) -> Path:
    return out / f"{table.replace('.', '__')}.json"


def _source(args: argparse.Namespace) -> Source:
    if args.engine == "postgres":
        return PostgresSource(args.dsn or _postgres_dsn())
    return DuckDBSource(args.database)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("postgres", "duckdb"), required=True)
    parser.add_argument("--tables", nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dsn", help="Postgres DSN; defaults to DW_POSTGRES_DSN")
    parser.add_argument(
        "--database",
        default=":memory:",
        help="DuckDB database path (used only with --engine duckdb)",
    )
    parser.add_argument(
        "--ordered-key",
        action="append",
        help="temporary ordered-key expression; repeat for each expression",
    )
    args = parser.parse_args()
    if args.ordered_key and len(args.tables) != 1:
        parser.error("--ordered-key requires exactly one table")
    if args.ordered_key and any(
        has_top_level_comma(expression) for expression in args.ordered_key
    ):
        parser.error(
            "--ordered-key accepts one expression per flag; "
            "pass the flag once per expression"
        )

    args.out.mkdir(parents=True, exist_ok=True)
    source = _source(args)
    try:
        for table in args.tables:
            columns = source.columns(table)
            ordered_expressions = (
                tuple(args.ordered_key)
                if args.ordered_key
                else ORDERED_KEYS.get(table)
            )
            ordered_key = (
                ", ".join(ordered_expressions) if ordered_expressions else None
            )
            with source.snapshot(table, columns) as reader:
                manifest = build(
                    table=table,
                    engine=args.engine,
                    columns=columns,
                    rows=reader.rows(),
                    profile_row=reader.profile(),
                    ordered_rows=(
                        reader.rows(order_by=ordered_key)
                        if ordered_key
                        else None
                    ),
                    ordered_key=ordered_key,
                    fingerprint=fingerprint_for(table),
                )
            path = manifest.write(_manifest_path(args.out, table))
            print(path)
    finally:
        source.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
