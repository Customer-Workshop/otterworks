-- Run 20260927c, unit pkg_invoicing: OW_BILLING.PKG_INVOICING -> billing.* (PL/pgSQL).
-- Source: services/legacy-billing/db/oracle/packages/04_pkg_invoicing.sql.
-- The package globals compute_preview publishes (g_plan_code, g_plan_fee, g_overage, g_credit, g_tax) become
-- the OUT record of billing.compute_preview. Tax lines carry g_tax/2 unrounded exactly as the cursor does;
-- NUMBER(12,2) / numeric(12,2) both round half away from zero on the insert.
-- sp_issue_invoice write order: rating_periods, rating_results (sp_finalize_rating), invoices, invoice_lines,
-- credit_notes, billing_audit_log.

CREATE OR REPLACE FUNCTION billing.compute_preview(
    p_tenant_id    varchar,
    p_period_start timestamp,
    p_period_end   timestamp,
    OUT plan_code  varchar,
    OUT plan_fee   numeric,
    OUT overage    numeric,
    OUT credit     numeric,
    OUT tax        numeric
)
LANGUAGE plpgsql
AS $$
DECLARE
    c_tax_rate constant numeric := 0.0825;
    v_exempt   char(1) := 'N';
    g          record;
BEGIN
    SELECT p.code, p.monthly_fee INTO plan_code, plan_fee
      FROM billing.subscriptions s
      JOIN billing.plans p ON p.id = s.plan_id
     WHERE s.tenant_id = p_tenant_id
       AND s.starts_on <= p_period_end
       AND (s.ends_on IS NULL OR s.ends_on >= p_period_start)
     ORDER BY s.starts_on DESC
     LIMIT 1;

    SELECT * INTO g FROM billing.compute_rating(p_tenant_id, p_period_start, p_period_end);
    overage := g.overage_amount;

    SELECT coalesce(sum(coalesce(cn.remaining_amount, 0)), 0) INTO credit
      FROM billing.credit_notes cn
     WHERE cn.tenant_id = p_tenant_id AND cn.remaining_amount > 0;

    SELECT coalesce(t.tax_exempt_yn, 'N') INTO v_exempt
      FROM billing.tenants t WHERE t.id = p_tenant_id;
    IF NOT FOUND THEN
        v_exempt := 'N';
    END IF;

    tax := CASE WHEN v_exempt = 'Y' THEN 0 ELSE (plan_fee + overage) * c_tax_rate END;
END;
$$;

CREATE OR REPLACE FUNCTION billing.fn_invoice_preview(p_tenant_id varchar, p_period_start timestamp, p_period_end timestamp)
RETURNS TABLE (
    line_no        integer,
    line_type      varchar,
    description    varchar,
    amount         numeric,
    tax_amount     numeric,
    credit_applied numeric,
    total          numeric
)
LANGUAGE plpgsql
AS $$
DECLARE
    g            record;
    v_charge_cap numeric;
    v_credit_app numeric;
BEGIN
    SELECT * INTO g FROM billing.compute_preview(p_tenant_id, p_period_start, p_period_end);
    v_charge_cap := round(g.plan_fee + g.overage + g.tax, 2);
    v_credit_app := least(g.credit, coalesce(v_charge_cap, g.credit));
    RETURN QUERY
        SELECT 1, 'plan'::varchar, g.plan_code::varchar, round(g.plan_fee, 2), 0::numeric, 0::numeric, round(g.plan_fee, 2)
        UNION ALL
        SELECT 2, 'usage'::varchar, 'usage overage'::varchar, round(g.overage, 2), 0::numeric, 0::numeric, round(g.overage, 2)
        UNION ALL
        SELECT 3, 'tax'::varchar, 'regional tax'::varchar, g.tax / 2, 0::numeric, 0::numeric, g.tax / 2
        UNION ALL
        SELECT 4, 'tax'::varchar, 'local tax'::varchar, g.tax / 2, 0::numeric, 0::numeric, g.tax / 2
        UNION ALL
        SELECT 5, 'credit'::varchar, 'credit notes'::varchar, 0::numeric, 0::numeric, v_credit_app, -v_credit_app;
END;
$$;

CREATE OR REPLACE FUNCTION billing.fn_invoice_lines(p_invoice_id varchar)
RETURNS TABLE (
    line_no     bigint,
    line_type   varchar,
    description varchar,
    amount      numeric
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
        SELECT il.line_no, il.line_type, il.description, il.amount
          FROM billing.invoice_lines il
         WHERE il.invoice_id = p_invoice_id
         ORDER BY il.line_no;
END;
$$;

CREATE OR REPLACE PROCEDURE billing.sp_issue_invoice(p_tenant_id varchar, p_period_start timestamp, p_period_end timestamp)
LANGUAGE plpgsql
AS $$
DECLARE
    v_period_id  varchar(36);
    v_invoice_id varchar(36);
    l            record;
    r            record;
    v_subtotal   numeric := 0;
    v_tax        numeric := 0;
    v_total      numeric := 0;
    v_credit     numeric := 0;
BEGIN
    v_period_id := billing.f_md5_uuid(p_tenant_id || to_char(p_period_start, 'YYYY-MM-DD'));
    v_invoice_id := billing.f_md5_uuid(v_period_id || 'invoice');

    CALL billing.sp_finalize_rating(p_tenant_id, p_period_start, p_period_end);

    BEGIN
        INSERT INTO billing.invoices (id, tenant_id, period_id, issued_at, subtotal, tax, total, status_cd)
        VALUES (v_invoice_id, p_tenant_id, v_period_id, p_period_end::timestamp(6), 0, 0, 0, 20);
    EXCEPTION
        WHEN unique_violation THEN
            UPDATE billing.invoices SET status_cd = 20 WHERE id = v_invoice_id;
    END;

    DELETE FROM billing.invoice_lines WHERE invoice_id = v_invoice_id;

    FOR l IN SELECT * FROM billing.fn_invoice_preview(p_tenant_id, p_period_start, p_period_end) LOOP
        INSERT INTO billing.invoice_lines (id, invoice_id, line_no, line_type, description, amount)
        VALUES (
            billing.f_md5_uuid(v_invoice_id || regexp_replace(regexp_replace(regexp_replace((l.line_no)::text, '(\.\d*?)0+$', '\1'), '\.$', ''), '^(-?)0\.', '\1.')),
            v_invoice_id, l.line_no, l.line_type, l.description,
            CASE l.line_type WHEN 'credit' THEN l.total ELSE l.amount END
        );
        IF l.line_type = 'plan' OR l.line_type = 'usage' THEN
            v_subtotal := v_subtotal + round(l.amount, 2);
        ELSIF l.line_type = 'tax' THEN
            v_tax := v_tax + round(l.amount, 2);
        ELSIF l.line_type = 'credit' THEN
            v_credit := l.credit_applied;
        END IF;
    END LOOP;

    v_total := round(v_subtotal + v_tax - v_credit, 2);
    UPDATE billing.invoices
       SET subtotal = round(v_subtotal, 2), tax = round(v_tax, 2), total = v_total
     WHERE id = v_invoice_id;

    -- burn credit notes oldest first; Oracle ORDER BY id is binary
    FOR r IN
        SELECT id, remaining_amount FROM billing.credit_notes
         WHERE tenant_id = p_tenant_id AND remaining_amount > 0
         ORDER BY issued_on, id COLLATE "C"
    LOOP
        EXIT WHEN v_credit <= 0;
        UPDATE billing.credit_notes
           SET remaining_amount = greatest(remaining_amount - v_credit, 0)
         WHERE id = r.id;
        v_credit := greatest(v_credit - r.remaining_amount, 0);
    END LOOP;

    CALL billing.log_msg('INVOICING', 'issued invoice=' || v_invoice_id ||
        ' total=' || regexp_replace(regexp_replace(regexp_replace((coalesce(v_total, 0))::text, '(\.\d*?)0+$', '\1'), '\.$', ''), '^(-?)0\.', '\1.'));
END;
$$;
