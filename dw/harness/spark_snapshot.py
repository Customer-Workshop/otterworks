"""Write a manifest for one Delta table using the Spark source adapter."""

from __future__ import annotations

import argparse
from pathlib import Path

from assets import fingerprint_for
from ordering import has_top_level_comma
from spark_runtime import local_spark
from spark_source import build_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--ordered-key",
        action="append",
        help="ordered-key expression; repeat for each expression",
    )
    args = parser.parse_args(argv)
    if args.ordered_key and any(
        has_top_level_comma(expression) for expression in args.ordered_key
    ):
        parser.error(
            "--ordered-key accepts one expression per flag; "
            "pass the flag once per expression"
        )
    spark = local_spark("spark-manifest")
    try:
        manifest = build_manifest(
            spark=spark,
            path=str(args.path),
            table=args.table,
            fingerprint=fingerprint_for(args.table),
            ordered_key=tuple(args.ordered_key) if args.ordered_key else None,
        )
        manifest.write(args.out)
        print(args.out)
    finally:
        spark.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
