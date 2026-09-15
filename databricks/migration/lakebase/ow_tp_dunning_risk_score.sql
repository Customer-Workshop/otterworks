-- Lakebase landing tables for the dunning-risk score (ow_tp database, schema billing).
--
-- The score is computed in Databricks (databricks/scoring/dunning_risk/) and published here
-- so the dunning process can read it in the same transaction as the invoices it is acting
-- on. Nothing in Lakebase computes a score; these tables are a read model.
--
-- Rerunning this file is a no-op: every object is created only if absent and every
-- constraint is added only if pg_constraint does not already hold it. It creates structure
-- and never touches rows - the data is loaded by
-- databricks/scoring/dunning_risk/sync_to_lakebase.py, which replaces the contents of all
-- three tables inside one transaction.
--
-- Types follow the pipeline-1 finding: Oracle DATE carries a time part and Oracle TIMESTAMP
-- is zoneless, so every point in time here is `timestamp` (no time zone). Money is
-- `numeric`, never a float.

CREATE TABLE IF NOT EXISTS billing.dunning_risk_rules (
    seq        smallint      NOT NULL,
    rule_id    varchar(40)   NOT NULL,
    signal     varchar(40)   NOT NULL,
    feature    varchar(40)   NOT NULL,
    condition  varchar(200)  NOT NULL,
    points     smallint      NOT NULL,
    rationale  varchar(400)  NOT NULL,
    CONSTRAINT pk_dunning_risk_rules PRIMARY KEY (rule_id)
);

COMMENT ON TABLE billing.dunning_risk_rules IS
    'The scored rule set that produced dunning_risk_invoice.risk_score. Sum of the points of the rules named in reason_codes, clamped to [0,100].';

CREATE TABLE IF NOT EXISTS billing.dunning_risk_invoice (
    invoice_id              varchar(36)    NOT NULL,
    invoice_no              varchar(30),
    cust_id                 varchar(36)    NOT NULL,
    tenant_id               varchar(36),
    status_cd               smallint       NOT NULL,
    legacy_dunning_eligible boolean        NOT NULL,
    total_amt               numeric(14, 2) NOT NULL,
    invoice_dt              timestamp,
    due_dt                  timestamp,
    due_before_invoice_dt   boolean        NOT NULL,
    age_days                integer,
    risk_score              smallint       NOT NULL,
    risk_band               varchar(10)    NOT NULL,
    reason_codes            text[]         NOT NULL,
    unscored_signals        text[]         NOT NULL,
    as_of_dt                date           NOT NULL,
    scored_at               timestamp      NOT NULL,
    CONSTRAINT pk_dunning_risk_invoice PRIMARY KEY (invoice_id),
    CONSTRAINT ck_dunning_risk_invoice_score CHECK (risk_score BETWEEN 0 AND 100),
    CONSTRAINT ck_dunning_risk_invoice_band
        CHECK (risk_band IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', 'EXEMPT'))
);

COMMENT ON TABLE billing.dunning_risk_invoice IS
    'Dunning-risk score per open invoice. An ordering input for the dunning process, not an instruction: no row here authorises an attempt, a suspension or a write-off.';
COMMENT ON COLUMN billing.dunning_risk_invoice.unscored_signals IS
    'Signals that could not be evaluated for this row, with the reason. A low score with a long list here means thin evidence, not low risk.';
COMMENT ON COLUMN billing.dunning_risk_invoice.due_before_invoice_dt IS
    'True where the migrated due date precedes the invoice date. Carried from the source as-is, not repaired.';

CREATE TABLE IF NOT EXISTS billing.dunning_risk_account (
    cust_id                 varchar(36)    NOT NULL,
    tenant_id               varchar(36),
    open_invoice_cnt        integer        NOT NULL,
    dunnable_invoice_cnt    integer        NOT NULL,
    open_amt                numeric(14, 2) NOT NULL,
    oldest_open_age_days    integer,
    worst_invoice_id        varchar(36),
    risk_score              smallint,
    risk_band               varchar(15)    NOT NULL,
    reason_codes            text[],
    unscored_signals        text[]         NOT NULL,
    lifetime_overdue_rate   numeric(9, 6),
    credit_hold_yn          char(1),
    vip_yn                  char(1),
    dunning_exempt_yn       char(1),
    tenure_days             integer,
    as_of_dt                date           NOT NULL,
    scored_at               timestamp      NOT NULL,
    CONSTRAINT pk_dunning_risk_account PRIMARY KEY (cust_id),
    CONSTRAINT ck_dunning_risk_account_score CHECK (risk_score IS NULL OR risk_score BETWEEN 0 AND 100)
);

COMMENT ON TABLE billing.dunning_risk_account IS
    'Dunning-risk score per billing account, carrying the score of its worst open invoice. Accounts with no open invoice are not published.';

-- Read paths the dunning process actually uses: "the queue, worst first" and "this account".
CREATE INDEX IF NOT EXISTS ix_dunning_risk_invoice_queue
    ON billing.dunning_risk_invoice (risk_score DESC, age_days DESC)
    WHERE legacy_dunning_eligible;
CREATE INDEX IF NOT EXISTS ix_dunning_risk_invoice_cust
    ON billing.dunning_risk_invoice (cust_id);
CREATE INDEX IF NOT EXISTS ix_dunning_risk_account_band
    ON billing.dunning_risk_account (risk_band);

-- No foreign key to billing.invoices. The invoice history that produced these scores is the
-- Delta estate keyed on customer_master, and billing.invoices on this branch holds 3 rows on
-- a tenant key space that does not intersect it. A FK here would fail on load and would be
-- asserting a relationship the migrated data does not currently have. Stated rather than
-- silently omitted; it should be added once the two key spaces are reconciled.
