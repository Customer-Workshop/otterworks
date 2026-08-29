"""Airflow-style dependency graph for the live legacy warehouse assets.

The module intentionally has no Airflow import so scanners and local runners
can inspect the graph without installing the production scheduler.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Task:
    task_id: str
    command: str
    upstream: list[str] = field(default_factory=list)


@dataclass
class DAG:
    dag_id: str
    schedule: str
    tasks: list[Task]

    def task_ids(self) -> set[str]:
        return {task.task_id for task in self.tasks}


CORE_TASKS = [
    ("merge_customer_scd2", "core.sp_merge_customer_scd2"),
    ("dim_customer_scd2", "core.dim_customer_scd2"),
    ("dim_product", "core.dim_product"),
    ("dim_date", "core.dim_date"),
    ("dim_store", "core.dim_store"),
    ("fct_orders", "core.fct_orders"),
    ("fct_order_items", "core.fct_order_items"),
    ("fct_web_events", "core.fct_web_events"),
    ("fct_returns", "core.fct_returns"),
    ("fx_rates_daily", "core.fx_rates_daily"),
]

MART_TASKS = [
    ("daily_revenue_by_channel", "mart.daily_revenue_by_channel"),
    ("daily_revenue_usd", "mart.daily_revenue_usd"),
    ("customer_ltv", "mart.customer_ltv"),
    ("product_performance_monthly", "mart.product_performance_monthly"),
    ("session_funnel_daily", "mart.session_funnel_daily"),
    ("cohort_retention_monthly", "mart.cohort_retention_monthly"),
    ("returns_rate_by_category", "mart.returns_rate_by_category"),
    ("top_products_by_category", "mart.top_products_by_category"),
]


def build_dag() -> DAG:
    tasks = [
        Task("merge_customer_scd2", "CALL core.sp_merge_customer_scd2()"),
        Task(
            "dim_customer_scd2",
            "elt/core_dim_customer_scd2.sql",
            ["merge_customer_scd2"],
        ),
        Task("load_orders_incremental", "CALL core.sp_load_orders_incremental()"),
        Task(
            "dim_product",
            "elt/core_dim_product.sql",
        ),
        Task("dim_date", "elt/core_dim_date.sql"),
        Task("dim_store", "elt/core_dim_store.sql", ["load_orders_incremental"]),
        Task("fct_orders", "elt/core_fct_orders.sql", ["load_orders_incremental"]),
        Task(
            "fct_order_items",
            "elt/core_fct_order_items.sql",
            ["fct_orders", "dim_product"],
        ),
        Task("fct_web_events", "elt/core_fct_web_events.sql"),
        Task("fct_returns", "elt/core_fct_returns.sql", ["fct_order_items", "fct_orders"]),
        Task("fx_rates_daily", "elt/core_fx_rates_daily.sql"),
        Task(
            "daily_revenue_by_channel",
            "elt/mart_daily_revenue_by_channel.sql",
            ["fct_orders"],
        ),
        Task(
            "daily_revenue_usd",
            "elt/mart_daily_revenue_usd.sql",
            ["fct_orders", "fx_rates_daily"],
        ),
        Task(
            "customer_ltv",
            "elt/mart_customer_ltv.sql",
            ["fct_orders", "dim_customer_scd2"],
        ),
        Task(
            "product_performance_monthly",
            "elt/mart_product_performance_monthly.sql",
            ["fct_order_items"],
        ),
        Task("session_funnel_daily", "elt/mart_session_funnel_daily.sql", ["fct_web_events"]),
        Task(
            "cohort_retention_monthly",
            "elt/mart_cohort_retention_monthly.sql",
            ["fct_web_events", "merge_customer_scd2"],
        ),
        Task(
            "returns_rate_by_category",
            "elt/mart_returns_rate_by_category.sql",
            ["fct_order_items", "fct_returns"],
        ),
        Task(
            "top_products_by_category",
            "elt/mart_top_products_by_category.sql",
            ["fct_order_items"],
        ),
        Task(
            "refresh_marts",
            "CALL core.sp_refresh_marts()",
            [
                "daily_revenue_by_channel",
                "daily_revenue_usd",
                "customer_ltv",
                "product_performance_monthly",
                "session_funnel_daily",
                "cohort_retention_monthly",
                "returns_rate_by_category",
                "top_products_by_category",
            ],
        ),
        Task(
            "housekeeping",
            "CALL core.sp_housekeeping()",
            ["refresh_marts"],
        ),
    ]
    return DAG("legacy_dw_nightly", "0 2 * * *", tasks)


dag = build_dag()
