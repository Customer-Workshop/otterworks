CREATE OR REPLACE PROCEDURE core.sp_merge_customer_scd2()
LANGUAGE plpgsql
AS $$
BEGIN
    CREATE TEMP TABLE customer_changes ON COMMIT DROP AS
    SELECT s.customer_id,
           s.customer_name,
           s.email,
           s.country_code,
           s.city,
           UPPER(s.segment) AS segment,
           s.marketing_opt_in,
           MD5(CONCAT_WS('|', s.customer_name, s.email, s.country_code,
                         s.city, UPPER(s.segment),
                         s.marketing_opt_in::VARCHAR)) AS hash_diff,
           s.load_ts AS effective_from
    FROM staging.stg_customers_raw s;

    UPDATE core.dim_customer_scd2 current_row
    SET effective_to = changes.effective_from,
        is_current = FALSE
    FROM customer_changes changes
    WHERE current_row.customer_id = changes.customer_id
      AND current_row.is_current
      AND current_row.hash_diff <> changes.hash_diff;

    INSERT INTO core.dim_customer_scd2
        (customer_sk, customer_id, customer_name, email, country_code, city,
         segment, marketing_opt_in, hash_diff, effective_from, effective_to,
         is_current)
    SELECT NEXTVAL('core.dim_customer_scd2_sk_seq'),
           changes.customer_id,
           changes.customer_name,
           changes.email,
           changes.country_code,
           changes.city,
           changes.segment,
           changes.marketing_opt_in,
           changes.hash_diff,
           changes.effective_from,
           TIMESTAMP '9999-12-31 00:00:00',
           TRUE
    FROM customer_changes changes
    LEFT JOIN core.dim_customer_scd2 current_row
      ON current_row.customer_id = changes.customer_id
     AND current_row.is_current
    WHERE current_row.customer_id IS NULL;
END;
$$;
