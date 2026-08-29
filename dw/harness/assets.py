"""Source-input inventory for the legacy and converted asset evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from fingerprints import fingerprint

ROOT = Path(__file__).resolve().parents[2]
ESTATE = ROOT / "dw/legacy-estate"
SEED = ESTATE / "seed/seed.sql"
RUNTIME_SOURCES = (
    ESTATE / "ddl/compat/redshift_to_postgres.py",
    ESTATE / "ddl/compat/shims.sql",
    ROOT / "dw/harness/manifest.py",
    ROOT / "dw/harness/digest.py",
    ROOT / "dw/harness/sources.py",
    ROOT / "dw/harness/spark_source.py",
)
CALL_STATEMENT = re.compile(
    r"\bCALL\s+(?P<schema>[a-z_]+)\.(?P<name>[a-z_][a-z0-9_]*)\s*\(",
    re.IGNORECASE,
)
PROCEDURE_DECLARATION = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+"
    r"(?P<schema>[a-z_]+)\.(?P<name>[a-z_][a-z0-9_]*)\s*\([^)]*\)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AssetSpec:
    elt: Path
    ddl: Path
    upstream: tuple[str, ...] = ()
    staging_ddls: tuple[Path, ...] = ()


def _ddl(*paths: str) -> tuple[Path, ...]:
    return tuple(ESTATE / "ddl" / path for path in paths)


ASSETS: dict[str, AssetSpec] = {
    "core.dim_customer_scd2": AssetSpec(
        ESTATE / "elt/core_dim_customer_scd2.sql",
        ESTATE / "ddl/core/dim_customer_scd2.sql",
        staging_ddls=_ddl("staging/stg_customers_raw.sql"),
    ),
    "core.dim_product": AssetSpec(
        ESTATE / "elt/core_dim_product.sql",
        ESTATE / "ddl/core/dim_product.sql",
        staging_ddls=_ddl("staging/stg_products_raw.sql"),
    ),
    "core.dim_date": AssetSpec(
        ESTATE / "elt/core_dim_date.sql",
        ESTATE / "ddl/core/dim_date.sql",
    ),
    "core.dim_store": AssetSpec(
        ESTATE / "elt/core_dim_store.sql",
        ESTATE / "ddl/core/dim_store.sql",
        staging_ddls=_ddl("staging/stg_orders_raw.sql"),
    ),
    "core.fct_orders": AssetSpec(
        ESTATE / "elt/core_fct_orders.sql",
        ESTATE / "ddl/core/fct_orders.sql",
        staging_ddls=_ddl("staging/stg_orders_raw.sql"),
    ),
    "core.fct_order_items": AssetSpec(
        ESTATE / "elt/core_fct_order_items.sql",
        ESTATE / "ddl/core/fct_order_items.sql",
        upstream=("core.fct_orders", "core.dim_product"),
        staging_ddls=_ddl(
            "staging/stg_order_items_raw.sql",
        ),
    ),
    "core.fct_web_events": AssetSpec(
        ESTATE / "elt/core_fct_web_events.sql",
        ESTATE / "ddl/core/fct_web_events.sql",
        staging_ddls=_ddl("staging/stg_web_events_raw.sql"),
    ),
    "core.fct_returns": AssetSpec(
        ESTATE / "elt/core_fct_returns.sql",
        ESTATE / "ddl/core/fct_returns.sql",
        upstream=("core.fct_order_items",),
        staging_ddls=_ddl(
            "staging/stg_returns_raw.sql",
        ),
    ),
    "core.fx_rates_daily": AssetSpec(
        ESTATE / "elt/core_fx_rates_daily.sql",
        ESTATE / "ddl/core/fx_rates_daily.sql",
        staging_ddls=_ddl("staging/stg_fx_rates_raw.sql"),
    ),
    "mart.daily_revenue_by_channel": AssetSpec(
        ESTATE / "elt/mart_daily_revenue_by_channel.sql",
        ESTATE / "ddl/mart/daily_revenue_by_channel.sql",
        upstream=("core.fct_orders",),
    ),
    "mart.daily_revenue_usd": AssetSpec(
        ESTATE / "elt/mart_daily_revenue_usd.sql",
        ESTATE / "ddl/mart/daily_revenue_usd.sql",
        upstream=("core.fct_orders", "core.fx_rates_daily"),
    ),
    "mart.customer_ltv": AssetSpec(
        ESTATE / "elt/mart_customer_ltv.sql",
        ESTATE / "ddl/mart/customer_ltv.sql",
        upstream=("core.fct_orders", "core.dim_customer_scd2"),
    ),
    "mart.product_performance_monthly": AssetSpec(
        ESTATE / "elt/mart_product_performance_monthly.sql",
        ESTATE / "ddl/mart/product_performance_monthly.sql",
        upstream=("core.fct_order_items",),
    ),
    "mart.session_funnel_daily": AssetSpec(
        ESTATE / "elt/mart_session_funnel_daily.sql",
        ESTATE / "ddl/mart/session_funnel_daily.sql",
        upstream=("core.fct_web_events",),
    ),
    "mart.cohort_retention_monthly": AssetSpec(
        ESTATE / "elt/mart_cohort_retention_monthly.sql",
        ESTATE / "ddl/mart/cohort_retention_monthly.sql",
        upstream=("core.fct_web_events", "core.dim_customer_scd2"),
    ),
    "mart.returns_rate_by_category": AssetSpec(
        ESTATE / "elt/mart_returns_rate_by_category.sql",
        ESTATE / "ddl/mart/returns_rate_by_category.sql",
        upstream=("core.fct_order_items", "core.fct_returns"),
    ),
    "mart.top_products_by_category": AssetSpec(
        ESTATE / "elt/mart_top_products_by_category.sql",
        ESTATE / "ddl/mart/top_products_by_category.sql",
        upstream=("core.fct_order_items",),
    ),
}


def _closure(table: str) -> tuple[AssetSpec, ...]:
    seen: set[str] = set()
    result: list[AssetSpec] = []

    def visit(key: str) -> None:
        if key in seen:
            return
        try:
            asset = ASSETS[key]
        except KeyError as error:
            raise ValueError(f"{table}: unknown upstream asset {key!r}") from error
        seen.add(key)
        result.append(asset)
        for upstream in asset.upstream:
            visit(upstream)

    visit(table)
    return tuple(result)


def _procedure_index() -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in sorted((ESTATE / "procs").glob("*.sql")):
        match = PROCEDURE_DECLARATION.search(path.read_text(errors="replace"))
        if match:
            result[
                f"{match.group('schema').lower()}.{match.group('name').lower()}"
            ] = path
    return result


def _procedure_closure(assets: tuple[AssetSpec, ...]) -> tuple[Path, ...]:
    index = _procedure_index()
    pending = [
        match
        for asset in assets
        for match in CALL_STATEMENT.finditer(
            asset.elt.read_text(errors="replace")
        )
    ]
    seen: set[Path] = set()
    result: list[Path] = []
    while pending:
        match = pending.pop()
        name = f"{match.group('schema').lower()}.{match.group('name').lower()}"
        try:
            path = index[name]
        except KeyError as error:
            raise ValueError(
                f"{match.group(0)}: no procedure declaration in estate"
            ) from error
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
        pending.extend(
            CALL_STATEMENT.finditer(path.read_text(errors="replace"))
        )
    return tuple(result)


def fingerprint_for(table: str) -> str:
    """Return the source fingerprint for one live core or mart asset."""
    if table not in ASSETS:
        raise ValueError(f"no fingerprint input map for top-level asset {table!r}")
    assets = _closure(table)
    procedures = _procedure_closure(assets)
    return fingerprint(
        asset_sources=tuple(asset.elt for asset in assets) + procedures,
        schema_sources=tuple(
            path
            for asset in assets
            for path in (asset.ddl, *asset.staging_ddls)
        ),
        seed_sources=(SEED,),
        runtime_sources=RUNTIME_SOURCES,
    )
