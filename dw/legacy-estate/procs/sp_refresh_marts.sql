CREATE OR REPLACE PROCEDURE core.sp_refresh_marts()
LANGUAGE plpgsql
AS $$
BEGIN
    ANALYZE mart.daily_revenue_by_channel;
    ANALYZE mart.daily_revenue_usd;
    ANALYZE mart.customer_ltv;
    ANALYZE mart.product_performance_monthly;
    ANALYZE mart.session_funnel_daily;
    ANALYZE mart.cohort_retention_monthly;
    ANALYZE mart.returns_rate_by_category;
    ANALYZE mart.top_products_by_category;
    RAISE NOTICE 'mart statistics refreshed at %', GETDATE();
END;
$$;
