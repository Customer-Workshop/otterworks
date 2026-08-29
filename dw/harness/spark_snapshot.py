"""Write a manifest for one Delta table using the Spark source adapter."""

from __future__ import annotations

import argparse
from pathlib import Path

from assets import fingerprint_for
from spark_runtime import local_spark
from spark_source import build_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ordered-key")
    args = parser.parse_args(argv)
    spark = local_spark("spark-manifest")
    try:
        manifest = build_manifest(
            spark=spark,
            path=str(args.path),
            table=args.table,
            fingerprint=fingerprint_for(args.table),
            ordered_key=args.ordered_key,
        )
        manifest.write(args.out)
        print(args.out)
    finally:
        spark.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
