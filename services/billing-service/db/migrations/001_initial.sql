CREATE SCHEMA IF NOT EXISTS billing_svc;

CREATE TABLE IF NOT EXISTS billing_svc.tenants (
    id uuid PRIMARY KEY,
    name text NOT NULL UNIQUE,
    tax_exempt boolean NOT NULL DEFAULT false,
    status text NOT NULL CHECK (status IN ('active', 'suspended'))
);

CREATE TABLE IF NOT EXISTS billing_svc.plans (
    id uuid PRIMARY KEY,
    code text NOT NULL UNIQUE,
    tier text NOT NULL CHECK (tier IN ('starter', 'growth', 'scale')),
    monthly_fee numeric(12, 2) NOT NULL CHECK (monthly_fee >= 0),
    included_units integer NOT NULL CHECK (included_units >= 0),
    overage_rate numeric(12, 6) NOT NULL CHECK (overage_rate >= 0),
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS billing_svc.subscriptions (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES billing_svc.tenants(id),
    plan_id uuid NOT NULL REFERENCES billing_svc.plans(id),
    starts_on date NOT NULL,
    ends_on date,
    status text NOT NULL CHECK (status IN ('active', 'suspended', 'cancelled')),
    suspended_on date,
    CHECK (ends_on IS NULL OR ends_on >= starts_on),
    CHECK (suspended_on IS NULL OR suspended_on >= starts_on)
);

CREATE TABLE IF NOT EXISTS billing_svc.rating_periods (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES billing_svc.tenants(id),
    period_start date NOT NULL,
    period_end date NOT NULL,
    UNIQUE (tenant_id, period_start),
    CHECK (period_end >= period_start)
);

CREATE TABLE IF NOT EXISTS billing_svc.invoices (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES billing_svc.tenants(id),
    period_id uuid NOT NULL REFERENCES billing_svc.rating_periods(id),
    issued_at timestamptz NOT NULL,
    subtotal numeric(12, 2) NOT NULL CHECK (subtotal >= 0),
    tax numeric(12, 2) NOT NULL CHECK (tax >= 0),
    total numeric(12, 2) NOT NULL CHECK (total >= 0),
    status text NOT NULL CHECK (status IN ('draft', 'issued', 'paid', 'overdue'))
);

CREATE TABLE IF NOT EXISTS billing_svc.dunning_attempts (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES billing_svc.tenants(id),
    invoice_id uuid NOT NULL REFERENCES billing_svc.invoices(id),
    attempt_no integer NOT NULL CHECK (attempt_no > 0),
    scheduled_for date NOT NULL,
    status text NOT NULL CHECK (status IN ('scheduled', 'sent', 'skipped')),
    UNIQUE (invoice_id, attempt_no)
);

CREATE TABLE IF NOT EXISTS billing_svc.notifications (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES billing_svc.tenants(id),
    kind text NOT NULL CHECK (kind IN ('invoice', 'dunning', 'suspension')),
    sent_at timestamptz NOT NULL,
    UNIQUE (tenant_id, kind, sent_at)
);
