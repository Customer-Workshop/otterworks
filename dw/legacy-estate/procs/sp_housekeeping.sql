CREATE OR REPLACE PROCEDURE core.sp_housekeeping()
LANGUAGE plpgsql
AS $$
BEGIN
    ANALYZE staging.stg_customers_raw;
    ANALYZE staging.stg_products_raw;
    ANALYZE staging.stg_orders_raw;
    ANALYZE staging.stg_order_items_raw;
    ANALYZE staging.stg_web_events_raw;
    ANALYZE staging.stg_returns_raw;
    ANALYZE staging.stg_fx_rates_raw;
    ANALYZE core.dim_customer_scd2;
    ANALYZE core.dim_product;
    ANALYZE core.dim_date;
    ANALYZE core.dim_store;
    ANALYZE core.fct_orders;
    ANALYZE core.fct_order_items;
    ANALYZE core.fct_web_events;
    ANALYZE core.fct_returns;
    ANALYZE core.fx_rates_daily;
    RAISE NOTICE 'legacy estate analyze completed at %', GETDATE();
END;
$$;
