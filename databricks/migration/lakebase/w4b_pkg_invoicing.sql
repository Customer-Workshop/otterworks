-- U-23 pkg_invoicing -> Lakebase PL/pgSQL (unit p1-pkg-invoicing, wave 4 batch b).
--
-- Oracle source: services/legacy-billing/db/oracle/packages/04_pkg_invoicing.sql (read-only).
-- MODERN invoice generation (D9-01): billing.invoices / billing.invoice_lines, not the legacy
-- INVOICE_HEADER / INVOICE_LINE pair that went to Delta in wave 1.
-- Idempotent: CREATE OR REPLACE only (P1-D6); this script creates no table.
--
-- Declared write targets for this unit: billing.sp_issue_invoice, billing.fn_invoice_preview
-- and billing.fn_invoice_lines. Runtime DML only, into tables earlier waves own the DDL for:
-- billing.invoices, billing.invoice_lines, billing.credit_notes, and - through the call to
-- billing.sp_finalize_rating (D-009) - billing.rating_periods, billing.rating_results,
-- billing.rating_state and billing.billing_audit_log. Nothing else is created, altered or
-- written here.
--
-- Entrypoint coverage: the package exposes four public members. Three are converted below.
-- The fourth, compute_preview, is a procedure whose whole output is the five package globals
-- (g_plan_code, g_plan_fee, g_overage, g_tax, g_credit); a converted object with no result
-- and no target row would be a fourth object outside the declared write targets, and the
-- globals it sets are exactly the columns fn_invoice_preview projects. It is therefore
-- inlined into fn_invoice_preview, which is how Oracle's own fn_invoice_preview reaches it,
-- and sp_issue_invoice reads the same values back out of fn_invoice_preview's result instead
-- of out of session state (P1-D4). Same treatment pkg_rating's compute_rating got in w4-d.
--
-- Dependencies called, never redefined: billing.sp_finalize_rating and billing.fn_usage_rating
-- (unit p1-pkg-rating, w4-d), billing.f_md5_uuid and billing.log_msg (wave 0), and
-- billing.usage_events (unit p1-usage-events-oltp, w4-c) through the rating functions. The
-- Delta copy ow_tp.silver.usage_events is never read here.

-- fn_invoice_preview: pkg_invoicing.fn_invoice_preview, with compute_preview inlined.
--
-- The Oracle function returns a SYS_REFCURSOR over five rows; the projection is the consumer
-- contract (D4-02 lists a shim over it) and is reproduced column for column, in order, with
-- the same names, the same line numbers and the same literal descriptions.
--
-- The overage is the recomputation, never the finalize-time value. Oracle's compute_preview
-- calls pkg_rating.compute_rating and then assigns g_overage := pkg_rating.g_overage_amount
-- unconditionally, so whatever sp_finalize_rating computed moments earlier is overwritten and
-- the invoice is built from the second computation. The converted preview does the same: it
-- calls billing.fn_usage_rating - Oracle's compute_rating, including the audit row it writes
-- (D-009) - and uses that result. billing.rating_state stays the explicit form of the
-- g_overage_amount hand-off (P1-D4), written by sp_finalize_rating in unit p1-pkg-rating;
-- reading it back here and preferring it over the recomputation would bill a stale overage
-- whenever usage lands between the two statements, which Oracle does not do.
--
-- Conversions:
--   * `ROWNUM <= 1` over an ordered inline view becomes ORDER BY starts_on DESC LIMIT 1, and
--     `WHEN NO_DATA_FOUND THEN NULL` is what plpgsql's SELECT INTO already does: no row
--     leaves plan code and plan fee NULL and the preview continues (P1-D2, not "fixed").
--   * The credit-note sum stays a row-at-a-time loop with the source's NVL, not SUM().
--   * DECODE(v_exempt,'Y',0,(g_plan_fee+g_overage)*TAX_RATE) becomes CASE. The source's own
--     comment is the specification: a NULL plan fee or a NULL overage must propagate to a
--     NULL tax, which `+` does on both engines.
--   * TAX_RATE stays the value the source hardcodes, 0.0825, as a named constant.
--   * LEAST propagates NULL in Oracle and ignores it in Postgres (trap 23). The source works
--     around its own trap with NVL(v_charge_cap, g_credit), and that NVL is kept verbatim;
--     with it, no operand of the LEAST can be NULL unless g_credit is, so the two engines
--     agree without further wrapping.
--   * ROUND stays exactly where the source puts it: on the plan and usage amounts, on the
--     charge cap, and nowhere else - the two tax rows are g_tax/2 unrounded, as in the source.
--   * The five branches are a UNION ALL of scalars in Oracle, which returns them in order in
--     practice; ORDER BY line_no makes that explicit rather than relying on it. No row's
--     content changes, and sp_issue_invoice's per-line accumulation is order-independent.
--   * Oracle reads an empty VARCHAR2 as NULL and Postgres does not, so the tenant id is
--     normalised with NULLIF (trap 1).
-- An earlier revision of this unit carried a fourth argument. Postgres treats an argument
-- list as part of the identity, so CREATE OR REPLACE would leave that overload in place and
-- the three-argument call would then resolve to neither. Drop it before creating.
DROP FUNCTION IF EXISTS billing.fn_invoice_preview(text, timestamp, timestamp, numeric);

CREATE OR REPLACE FUNCTION billing.fn_invoice_preview(p_tenant_id text,
                                                      p_period_start timestamp,
                                                      p_period_end timestamp)
RETURNS TABLE (
    line_no        integer,
    line_type      text,
    description    text,
    amount         numeric,
    tax_amount     numeric,
    credit_applied numeric,
    total          numeric
)
LANGUAGE plpgsql
AS $$
DECLARE
    -- The 2011 combined rate the source hardcodes at 04_pkg_invoicing.sql:26.
    c_tax_rate   constant numeric := 0.0825;
    v_tenant_id  text := NULLIF(p_tenant_id, '');
    v_plan_code  varchar(50);
    v_plan_fee   numeric;
    v_overage    numeric;
    v_credit     numeric := 0;
    v_tax        numeric;
    v_exempt     char(1) := 'N';
    v_charge_cap numeric;
    v_credit_app numeric;
    v_rating     record;
    r            record;
BEGIN
    SELECT p.code, p.monthly_fee
      INTO v_plan_code, v_plan_fee
      FROM billing.subscriptions s
      JOIN billing.plans p ON p.id = s.plan_id
     WHERE s.tenant_id = v_tenant_id
       AND s.starts_on <= p_period_end
       AND (s.ends_on IS NULL OR s.ends_on >= p_period_start)
     ORDER BY s.starts_on DESC
     LIMIT 1;

    -- pkg_rating.compute_rating, then the g_overage_amount read.
    SELECT * INTO v_rating
      FROM billing.fn_usage_rating(v_tenant_id, p_period_start, p_period_end);
    v_overage := v_rating.overage_amount;

    -- Open credit notes, summed one row at a time.
    FOR r IN SELECT cn.remaining_amount
               FROM billing.credit_notes cn
              WHERE cn.tenant_id = v_tenant_id
                AND cn.remaining_amount > 0 LOOP
        v_credit := v_credit + COALESCE(r.remaining_amount, 0);
    END LOOP;

    SELECT COALESCE(t.tax_exempt_yn, 'N')
      INTO v_exempt
      FROM billing.tenants t
     WHERE t.id = v_tenant_id;
    IF NOT FOUND THEN
        v_exempt := 'N';
    END IF;

    v_tax := CASE WHEN v_exempt = 'Y' THEN 0
                  ELSE (v_plan_fee + v_overage) * c_tax_rate END;

    v_charge_cap := round(v_plan_fee + v_overage + v_tax, 2);
    v_credit_app := LEAST(v_credit, COALESCE(v_charge_cap, v_credit));

    RETURN QUERY
        SELECT 1, 'plan'::text, v_plan_code::text, round(v_plan_fee, 2),
               0::numeric, 0::numeric, round(v_plan_fee, 2)
        UNION ALL
        SELECT 2, 'usage', 'usage overage', round(v_overage, 2),
               0::numeric, 0::numeric, round(v_overage, 2)
        UNION ALL
        SELECT 3, 'tax', 'regional tax', v_tax / 2, 0::numeric, 0::numeric, v_tax / 2
        UNION ALL
        SELECT 4, 'tax', 'local tax', v_tax / 2, 0::numeric, 0::numeric, v_tax / 2
        UNION ALL
        SELECT 5, 'credit', 'credit notes', 0::numeric, 0::numeric,
               v_credit_app, -v_credit_app
        ORDER BY 1;
END;
$$;

COMMENT ON FUNCTION billing.fn_invoice_preview(text, timestamp, timestamp) IS
    'Migration unit p1-pkg-invoicing (U-23) from Oracle pkg_invoicing.fn_invoice_preview, '
    'with compute_preview inlined: the overage is billing.fn_usage_rating''s result, the '
    'recomputation Oracle also uses, not the finalize-time billing.rating_state value.';

-- fn_invoice_lines: pkg_invoicing.fn_invoice_lines.
--
-- A SYS_REFCURSOR over one table, reproduced as a table function with the same four columns
-- in the same order and the same ORDER BY. Empty-string id normalised with NULLIF (trap 1).
CREATE OR REPLACE FUNCTION billing.fn_invoice_lines(p_invoice_id text)
RETURNS TABLE (
    line_no     integer,
    line_type   varchar(10),
    description varchar(400),
    amount      numeric(12,2)
)
LANGUAGE sql
STABLE
AS $$
    SELECT il.line_no, il.line_type, il.description, il.amount
      FROM billing.invoice_lines il
     WHERE il.invoice_id = NULLIF(p_invoice_id, '')
     ORDER BY il.line_no;
$$;

COMMENT ON FUNCTION billing.fn_invoice_lines(text) IS
    'Migration unit p1-pkg-invoicing (U-23) from Oracle pkg_invoicing.fn_invoice_lines.';

-- sp_issue_invoice: pkg_invoicing.sp_issue_invoice.
--
-- Conversions:
--   * The derived ids are unchanged: period id = f_md5_uuid(tenant || 'YYYY-MM-DD' of the
--     period start), invoice id = f_md5_uuid(period id || 'invoice'), line id =
--     f_md5_uuid(invoice id || line number). concat() folds NULL to '' the way Oracle's `||`
--     does, so a NULL tenant id derives the same id on both engines.
--   * pkg_rating.sp_finalize_rating is CALLed, not re-converted; the rating tables and the
--     rating_state row it writes are this batch's declared runtime writes (D-009).
--     The g_overage_amount hand-off it writes to billing.rating_state (P1-D4) is state that
--     belongs to that unit; this procedure does not read it back, because Oracle does not:
--     compute_preview overwrites the global with its own compute_rating call, so the invoice
--     is built from the recomputation, not from what finalize stored.
--   * INSERT-then-catch-DUP_VAL_ON_INDEX stays insert-then-catch, on unique_violation, rather
--     than becoming ON CONFLICT: the source's UPDATE branch sets only status_cd and must not
--     reset subtotal/tax/total to the zeros the INSERT carries.
--   * EXECUTE IMMEDIATE 'DELETE FROM invoice_lines WHERE invoice_id = :1' is a plain
--     parameterised DELETE. The SQL text is constant in the source, so the dynamic form
--     carries no behaviour; the rows removed are identical.
--   * The five preview rows are consumed in a loop, as the source consumes its cursor, and
--     the credit line is stored from v_line_total (the negative), not from v_amount - the
--     source's DECODE(v_line_type,'credit',v_line_total,v_amount).
--   * Rounding is applied per line (ROUND on each accumulated amount) AND again on the total
--     and on the subtotal/tax written to the header. Both roundings are kept.
--   * The credit burn-down keeps the source's quirk verbatim (04_pkg_invoicing.sql:180-190):
--     the running counter is decremented by the row's ORIGINAL remaining_amount, read before
--     the UPDATE, so the second and later notes see a counter that was never reduced by what
--     the first note could actually absorb. Ordering stays `issued_on, id`.
--   * Oracle's GREATEST returns NULL if any argument is NULL, Postgres' ignores NULLs (trap
--     23). Here g_credit can be NULL (a NULL credit_applied from a NULL charge cap), and the
--     source would then write NULL into a NOT NULL column and fail with ORA-01400. The NULL
--     is made explicit so the converted procedure fails the same way instead of silently
--     writing 0.
--   * log_msg's audit write is kept (D-009). Oracle's TO_CHAR(number) with no format drops a
--     trailing '.00' and a leading zero ('100', '.5'), which numeric::text does not, so the
--     text is normalised to Oracle's form - the message body is part of the behaviour.
--   * CAST(p_period_end AS TIMESTAMP) is a plain zoneless timestamp on both sides (D-010).
CREATE OR REPLACE PROCEDURE billing.sp_issue_invoice(p_tenant_id text,
                                                     p_period_start timestamp,
                                                     p_period_end timestamp)
LANGUAGE plpgsql
AS $$
DECLARE
    v_tenant_id  text := NULLIF(p_tenant_id, '');
    v_period_id  varchar(36);
    v_invoice_id varchar(36);
    v_subtotal   numeric := 0;
    v_tax        numeric := 0;
    v_total      numeric := 0;
    v_credit     numeric := 0;
    v_total_txt  text;
    r            record;
BEGIN
    v_period_id := billing.f_md5_uuid(
        concat(v_tenant_id, to_char(p_period_start, 'YYYY-MM-DD')));
    v_invoice_id := billing.f_md5_uuid(concat(v_period_id, 'invoice'));

    CALL billing.sp_finalize_rating(v_tenant_id, p_period_start, p_period_end);

    BEGIN
        INSERT INTO billing.invoices (
            id, tenant_id, period_id, issued_at, subtotal, tax, total, status_cd
        ) VALUES (
            v_invoice_id, v_tenant_id, v_period_id,
            p_period_end::timestamp, 0, 0, 0, 20
        );
    EXCEPTION
        WHEN unique_violation THEN
            UPDATE billing.invoices SET status_cd = 20 WHERE id = v_invoice_id;
    END;

    -- Rebuild the lines from scratch on every issue.
    DELETE FROM billing.invoice_lines WHERE invoice_id = v_invoice_id;

    FOR r IN SELECT *
               FROM billing.fn_invoice_preview(v_tenant_id, p_period_start,
                                               p_period_end) LOOP
        INSERT INTO billing.invoice_lines (
            id, invoice_id, line_no, line_type, description, amount
        ) VALUES (
            billing.f_md5_uuid(concat(v_invoice_id, r.line_no::text)),
            v_invoice_id, r.line_no, r.line_type, r.description,
            CASE WHEN r.line_type = 'credit' THEN r.total ELSE r.amount END
        );
        IF r.line_type = 'plan' OR r.line_type = 'usage' THEN
            v_subtotal := v_subtotal + round(r.amount, 2);
        ELSIF r.line_type = 'tax' THEN
            v_tax := v_tax + round(r.amount, 2);
        ELSIF r.line_type = 'credit' THEN
            v_credit := r.credit_applied;
        END IF;
    END LOOP;

    v_total := round(v_subtotal + v_tax - v_credit, 2);
    UPDATE billing.invoices
       SET subtotal = round(v_subtotal, 2),
           tax      = round(v_tax, 2),
           total    = v_total
     WHERE id = v_invoice_id;

    -- Burn down credit notes oldest-first, decrementing the same running counter the source
    -- does: r.remaining_amount is the value read before this row's own UPDATE.
    FOR r IN SELECT cn.id, cn.remaining_amount
               FROM billing.credit_notes cn
              WHERE cn.tenant_id = v_tenant_id
                AND cn.remaining_amount > 0
              ORDER BY cn.issued_on, cn.id LOOP
        EXIT WHEN v_credit <= 0;
        UPDATE billing.credit_notes
           SET remaining_amount = CASE
                   WHEN remaining_amount IS NULL OR v_credit IS NULL THEN NULL
                   ELSE GREATEST(remaining_amount - v_credit, 0) END
         WHERE id = r.id;
        v_credit := CASE
            WHEN v_credit IS NULL OR r.remaining_amount IS NULL THEN NULL
            ELSE GREATEST(v_credit - r.remaining_amount, 0) END;
    END LOOP;

    -- Oracle's TO_CHAR(NVL(v_total, 0)) with no format mask.
    v_total_txt := COALESCE(v_total, 0)::text;
    IF strpos(v_total_txt, '.') > 0 THEN
        v_total_txt := regexp_replace(v_total_txt, '0+$', '');
        v_total_txt := regexp_replace(v_total_txt, '\.$', '');
    END IF;
    v_total_txt := regexp_replace(v_total_txt, '^(-?)0\.', '\1.');

    PERFORM billing.log_msg('INVOICING', concat('issued invoice=', v_invoice_id,
        ' total=', v_total_txt));
END;
$$;

COMMENT ON PROCEDURE billing.sp_issue_invoice(text, timestamp, timestamp) IS
    'Migration unit p1-pkg-invoicing (U-23) from Oracle pkg_invoicing.sp_issue_invoice, the '
    'modern invoice generation (D9-01). Calls billing.sp_finalize_rating, whose '
    'billing.rating_state hand-off (P1-D4) the preview recomputes as Oracle does; keeps the '
    'log_msg audit write (D-009).';
