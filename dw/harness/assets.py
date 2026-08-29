"""Source-input inventory for the legacy and converted asset evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fingerprints import fingerprint

ROOT = Path(__file__).resolve().parents[2]
ESTATE = ROOT / "dw/legacy-estate"
SEED = ESTATE / "seed/seed.sql"


@dataclass(frozen=True)
class AssetInputs:
    elt: Path
    ddl: Path
    read_ddls: tuple[Path, ...]


def _ddl(*paths: str) -> tuple[Path, ...]:
    return tuple(ESTATE / "ddl" / path for path in paths)


ASSETS: dict[str, AssetInputs] = {
    "core.dim_customer_scd2": AssetInputs(
        ESTATE / "elt/core_dim_customer_scd2.sql",
        ESTATE / "ddl/core/dim_customer_scd2.sql",
        _ddl("staging/stg_customers_raw.sql"),
    ),
    "core.dim_product": AssetInputs(
        ESTATE / "elt/core_dim_product.sql",
        ESTATE / "ddl/core/dim_product.sql",
        _ddl("staging/stg_products_raw.sql"),
    ),
    "core.dim_date": AssetInputs(
        ESTATE / "elt/core_dim_date.sql",
        ESTATE / "ddl/core/dim_date.sql",
        (),
    ),
    "core.dim_store": AssetInputs(
        ESTATE / "elt/core_dim_store.sql",
        ESTATE / "ddl/core/dim_store.sql",
        _ddl("staging/stg_orders_raw.sql"),
    ),
    "core.fct_orders": AssetInputs(
        ESTATE / "elt/core_fct_orders.sql",
        ESTATE / "ddl/core/fct_orders.sql",
        _ddl("staging/stg_orders_raw.sql"),
    ),
    "core.fct_order_items": AssetInputs(
        ESTATE / "elt/core_fct_order_items.sql",
        ESTATE / "ddl/core/fct_order_items.sql",
        _ddl(
            "core/fct_orders.sql",
            "core/dim_product.sql",
            "staging/stg_order_items_raw.sql",
            "staging/stg_orders_raw.sql",
            "staging/stg_products_raw.sql",
        ),
    ),
    "core.fct_web_events": AssetInputs(
        ESTATE / "elt/core_fct_web_events.sql",
        ESTATE / "ddl/core/fct_web_events.sql",
        _ddl("staging/stg_web_events_raw.sql"),
    ),
    "core.fct_returns": AssetInputs(
        ESTATE / "elt/core_fct_returns.sql",
        ESTATE / "ddl/core/fct_returns.sql",
        _ddl(
            "core/fct_order_items.sql",
            "core/fct_orders.sql",
            "core/dim_product.sql",
            "staging/stg_returns_raw.sql",
            "staging/stg_order_items_raw.sql",
            "staging/stg_orders_raw.sql",
            "staging/stg_products_raw.sql",
        ),
    ),
    "core.fx_rates_daily": AssetInputs(
        ESTATE / "elt/core_fx_rates_daily.sql",
        ESTATE / "ddl/core/fx_rates_daily.sql",
        _ddl("staging/stg_fx_rates_raw.sql"),
    ),
    "mart.daily_revenue_by_channel": AssetInputs(
        ESTATE / "elt/mart_daily_revenue_by_channel.sql",
        ESTATE / "ddl/mart/daily_revenue_by_channel.sql",
        _ddl("core/fct_orders.sql", "staging/stg_orders_raw.sql"),
    ),
    "mart.daily_revenue_usd": AssetInputs(
        ESTATE / "elt/mart_daily_revenue_usd.sql",
        ESTATE / "ddl/mart/daily_revenue_usd.sql",
        _ddl(
            "core/fct_orders.sql",
            "core/fx_rates_daily.sql",
            "staging/stg_orders_raw.sql",
            "staging/stg_fx_rates_raw.sql",
        ),
    ),
    "mart.customer_ltv": AssetInputs(
        ESTATE / "elt/mart_customer_ltv.sql",
        ESTATE / "ddl/mart/customer_ltv.sql",
        _ddl(
            "core/fct_orders.sql",
            "core/dim_customer_scd2.sql",
            "staging/stg_orders_raw.sql",
            "staging/stg_customers_raw.sql",
        ),
    ),
    "mart.product_performance_monthly": AssetInputs(
        ESTATE / "elt/mart_product_performance_monthly.sql",
        ESTATE / "ddl/mart/product_performance_monthly.sql",
        _ddl(
            "core/fct_order_items.sql",
            "core/fct_orders.sql",
            "core/dim_product.sql",
            "staging/stg_order_items_raw.sql",
            "staging/stg_orders_raw.sql",
            "staging/stg_products_raw.sql",
        ),
    ),
    "mart.session_funnel_daily": AssetInputs(
        ESTATE / "elt/mart_session_funnel_daily.sql",
        ESTATE / "ddl/mart/session_funnel_daily.sql",
        _ddl("core/fct_web_events.sql", "staging/stg_web_events_raw.sql"),
    ),
    "mart.cohort_retention_monthly": AssetInputs(
        ESTATE / "elt/mart_cohort_retention_monthly.sql",
        ESTATE / "ddl/mart/cohort_retention_monthly.sql",
        _ddl(
            "core/fct_web_events.sql",
            "core/dim_customer_scd2.sql",
            "staging/stg_web_events_raw.sql",
            "staging/stg_customers_raw.sql",
        ),
    ),
    "mart.returns_rate_by_category": AssetInputs(
        ESTATE / "elt/mart_returns_rate_by_category.sql",
        ESTATE / "ddl/mart/returns_rate_by_category.sql",
        _ddl(
            "core/fct_order_items.sql",
            "core/fct_returns.sql",
            "core/fct_orders.sql",
            "core/dim_product.sql",
            "staging/stg_order_items_raw.sql",
            "staging/stg_returns_raw.sql",
            "staging/stg_orders_raw.sql",
            "staging/stg_products_raw.sql",
        ),
    ),
    "mart.top_products_by_category": AssetInputs(
        ESTATE / "elt/mart_top_products_by_category.sql",
        ESTATE / "ddl/mart/top_products_by_category.sql",
        _ddl(
            "core/fct_order_items.sql",
            "core/fct_orders.sql",
            "core/dim_product.sql",
            "staging/stg_order_items_raw.sql",
            "staging/stg_orders_raw.sql",
            "staging/stg_products_raw.sql",
        ),
    ),
}


def fingerprint_for(table: str) -> str:
    """Return the source fingerprint for one live core or mart asset."""
    try:
        asset = ASSETS[table]
    except KeyError as error:
        raise ValueError(f"no fingerprint input map for {table!r}") from error
    return fingerprint(
        asset_sources=(asset.elt,),
        schema_sources=(asset.ddl, *asset.read_ddls),
        seed_sources=(SEED,),
    )
