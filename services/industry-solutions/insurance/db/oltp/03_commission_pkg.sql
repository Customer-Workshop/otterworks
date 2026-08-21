-- Commission Pay business logic.
--
-- The rules no longer live here: they were extracted into the application-tier
-- commission-service (../../commission-service/app/domain.py, rule numbers as in
-- ../../RULE_LEDGER.md). This package body is a thin delegate — it marshals its
-- arguments to that service over HTTP, unmarshals the reply, and re-raises the
-- ORA-20xxx code and message the service decided on, so existing callers of
-- COMMISSION_PKG keep the exact same contract. Nothing below makes a business
-- decision, and no rule is stated in two places.
WHENEVER SQLERROR EXIT SQL.SQLCODE
-- The delegate builds query strings containing '&'; without this SQL*Plus would
-- read them as substitution variables and prompt while compiling the body.
SET DEFINE OFF

CREATE OR REPLACE TYPE split_alloc_t AS OBJECT (
    agent_id  NUMBER,
    split_pct NUMBER
);
/

CREATE OR REPLACE TYPE split_alloc_tab AS TABLE OF split_alloc_t;
/

CREATE OR REPLACE PACKAGE commission_pkg AS

    e_invalid_rate      EXCEPTION;
    e_unknown_agent     EXCEPTION;
    e_inactive_agent    EXCEPTION;
    e_unknown_product   EXCEPTION;
    e_unknown_policy    EXCEPTION;
    e_bad_split         EXCEPTION;
    e_no_rate           EXCEPTION;
    e_policy_not_active EXCEPTION;

    PRAGMA EXCEPTION_INIT(e_invalid_rate,      -20001);
    PRAGMA EXCEPTION_INIT(e_unknown_agent,     -20002);
    PRAGMA EXCEPTION_INIT(e_inactive_agent,    -20003);
    PRAGMA EXCEPTION_INIT(e_unknown_product,   -20004);
    PRAGMA EXCEPTION_INIT(e_unknown_policy,    -20005);
    PRAGMA EXCEPTION_INIT(e_bad_split,         -20006);
    PRAGMA EXCEPTION_INIT(e_no_rate,           -20007);
    PRAGMA EXCEPTION_INIT(e_policy_not_active, -20008);

    -- Create or supersede a commission rate. agent_id NULL sets the product
    -- default. The currently-open rate for the same (product, agent) scope is
    -- closed the day before p_effective_from; history is never deleted.
    PROCEDURE upsert_commission_rate (
        p_product_code   IN commission_rates.product_code%TYPE,
        p_agent_id       IN commission_rates.agent_id%TYPE,
        p_rate_pct       IN commission_rates.rate_pct%TYPE,
        p_effective_from IN DATE,
        p_actor          IN VARCHAR2,
        o_rate_id        OUT commission_rates.rate_id%TYPE
    );

    -- Close the open rate for a (product, agent) scope as of p_effective_to.
    PROCEDURE end_commission_rate (
        p_product_code IN commission_rates.product_code%TYPE,
        p_agent_id     IN commission_rates.agent_id%TYPE,
        p_effective_to IN DATE,
        p_actor        IN VARCHAR2
    );

    -- Replace the split allocation for a policy. Enforces: at least one agent,
    -- no duplicate agents, every agent ACTIVE, percentages each in (0, 100]
    -- and summing to exactly 100.00.
    PROCEDURE set_commission_splits (
        p_policy_id IN policies.policy_id%TYPE,
        p_splits    IN split_alloc_tab,
        p_actor     IN VARCHAR2
    );

    -- Resolve the rate in force for an agent on a product at a given date:
    -- the agent-specific rate wins over the product default.
    FUNCTION resolve_rate (
        p_product_code IN commission_rates.product_code%TYPE,
        p_agent_id     IN commission_rates.agent_id%TYPE,
        p_as_of        IN DATE
    ) RETURN commission_rates.rate_id%TYPE;

    -- Compute the commission ledger rows for a policy for a period (YYYY-MM).
    -- Commission per agent = annual_premium / 12 * rate_pct / 100 * split_pct
    -- / 100, rounded half-up to cents per agent row. Re-running a period for
    -- a policy replaces its rows.
    PROCEDURE calculate_policy_commission (
        p_policy_id    IN policies.policy_id%TYPE,
        p_period_month IN VARCHAR2,
        p_actor        IN VARCHAR2
    );

END commission_pkg;
/

CREATE OR REPLACE PACKAGE BODY commission_pkg AS

    -- The extracted rule owner. Resolvable on the fixture's Compose network;
    -- the network ACL that permits these callouts is granted in
    -- ../setup/02_service_acl.sql.
    c_service_url CONSTANT VARCHAR2(200) := 'http://commission-service:8000';
    c_timeout_s   CONSTANT PLS_INTEGER   := 60;
    c_date_fmt    CONSTANT VARCHAR2(30)  := 'YYYY-MM-DD HH24:MI:SS';

    -- Marshals a call to the rule owner and re-raises its verdict. A 200 hands
    -- back the response body; an application error is re-raised with the code
    -- and message the service chose, so callers see the same ORA-20xxx they saw
    -- when the rules ran in this package.
    FUNCTION call_service (
        p_path   IN VARCHAR2,
        p_method IN VARCHAR2,
        p_body   IN VARCHAR2 DEFAULT NULL
    ) RETURN CLOB IS
        l_req    UTL_HTTP.req;
        l_res    UTL_HTTP.resp;
        l_chunk  VARCHAR2(32767);
        l_reply  CLOB;
        l_status PLS_INTEGER;
        l_code   NUMBER;
        l_msg    VARCHAR2(1800);
    BEGIN
        UTL_HTTP.set_transfer_timeout(c_timeout_s);
        l_req := UTL_HTTP.begin_request(c_service_url || p_path, p_method, UTL_HTTP.HTTP_VERSION_1_1);
        UTL_HTTP.set_header(l_req, 'Accept', 'application/json');
        IF p_body IS NOT NULL THEN
            UTL_HTTP.set_header(l_req, 'Content-Type', 'application/json');
            UTL_HTTP.set_header(l_req, 'Content-Length', LENGTHB(p_body));
            UTL_HTTP.write_text(l_req, p_body);
        ELSE
            UTL_HTTP.set_header(l_req, 'Content-Length', 0);
        END IF;

        l_res := UTL_HTTP.get_response(l_req);
        l_status := l_res.status_code;
        DBMS_LOB.createtemporary(l_reply, TRUE);
        BEGIN
            LOOP
                UTL_HTTP.read_text(l_res, l_chunk, 32767);
                EXIT WHEN l_chunk IS NULL;
                DBMS_LOB.writeappend(l_reply, LENGTH(l_chunk), l_chunk);
            END LOOP;
        EXCEPTION
            WHEN UTL_HTTP.end_of_body THEN NULL;
        END;
        UTL_HTTP.end_response(l_res);

        IF l_status = 200 THEN
            RETURN l_reply;
        END IF;

        l_code := JSON_VALUE(l_reply, '$.ora_code' RETURNING NUMBER);
        l_msg  := JSON_VALUE(l_reply, '$.message' RETURNING VARCHAR2(1800));
        IF l_code BETWEEN -20999 AND -20001 THEN
            RAISE_APPLICATION_ERROR(l_code, l_msg);
        END IF;
        RAISE_APPLICATION_ERROR(-20000,
            'commission-service HTTP ' || l_status || ': '
            || NVL(l_msg, DBMS_LOB.SUBSTR(l_reply, 1000, 1)));
    END call_service;

    PROCEDURE upsert_commission_rate (
        p_product_code   IN commission_rates.product_code%TYPE,
        p_agent_id       IN commission_rates.agent_id%TYPE,
        p_rate_pct       IN commission_rates.rate_pct%TYPE,
        p_effective_from IN DATE,
        p_actor          IN VARCHAR2,
        o_rate_id        OUT commission_rates.rate_id%TYPE
    ) IS
        l_body  VARCHAR2(4000);
        l_reply CLOB;
    BEGIN
        SELECT JSON_OBJECT(
                   'product_code'   VALUE p_product_code,
                   'agent_id'       VALUE p_agent_id,
                   'rate_pct'       VALUE TO_CHAR(p_rate_pct),
                   'effective_from' VALUE TO_CHAR(p_effective_from, c_date_fmt),
                   'actor'          VALUE p_actor
                   NULL ON NULL)
          INTO l_body
          FROM dual;
        l_reply := call_service('/rates/upsert', 'POST', l_body);
        o_rate_id := JSON_VALUE(l_reply, '$.rate_id' RETURNING NUMBER);
    END upsert_commission_rate;

    PROCEDURE end_commission_rate (
        p_product_code IN commission_rates.product_code%TYPE,
        p_agent_id     IN commission_rates.agent_id%TYPE,
        p_effective_to IN DATE,
        p_actor        IN VARCHAR2
    ) IS
        l_body  VARCHAR2(4000);
        l_reply CLOB;
    BEGIN
        SELECT JSON_OBJECT(
                   'product_code' VALUE p_product_code,
                   'agent_id'     VALUE p_agent_id,
                   'effective_to' VALUE TO_CHAR(p_effective_to, c_date_fmt),
                   'actor'        VALUE p_actor
                   NULL ON NULL)
          INTO l_body
          FROM dual;
        l_reply := call_service('/rates/end', 'POST', l_body);
    END end_commission_rate;

    PROCEDURE set_commission_splits (
        p_policy_id IN policies.policy_id%TYPE,
        p_splits    IN split_alloc_tab,
        p_actor     IN VARCHAR2
    ) IS
        l_allocations VARCHAR2(32000) := '[';
        l_body        VARCHAR2(32000);
        l_reply       CLOB;
    BEGIN
        -- Collection order is preserved: the service applies the allocation in
        -- the order the caller supplied it.
        FOR i IN 1 .. NVL(p_splits.COUNT, 0) LOOP
            IF i > 1 THEN
                l_allocations := l_allocations || ',';
            END IF;
            l_allocations := l_allocations
                || '{"agent_id":' || NVL(TO_CHAR(p_splits(i).agent_id), 'null')
                || ',"split_pct":'
                || CASE
                       WHEN p_splits(i).split_pct IS NULL THEN 'null'
                       ELSE '"' || TO_CHAR(p_splits(i).split_pct) || '"'
                   END
                || '}';
        END LOOP;
        l_allocations := l_allocations || ']';

        SELECT JSON_OBJECT(
                   'splits' VALUE l_allocations FORMAT JSON,
                   'actor'  VALUE p_actor
                   NULL ON NULL)
          INTO l_body
          FROM dual;
        l_reply := call_service('/policies/' || p_policy_id || '/splits', 'POST', l_body);
    END set_commission_splits;

    FUNCTION resolve_rate (
        p_product_code IN commission_rates.product_code%TYPE,
        p_agent_id     IN commission_rates.agent_id%TYPE,
        p_as_of        IN DATE
    ) RETURN commission_rates.rate_id%TYPE IS
        l_reply CLOB;
    BEGIN
        l_reply := call_service(
            '/rates/resolve'
            || '?product_code=' || UTL_URL.escape(p_product_code, TRUE)
            || CASE WHEN p_agent_id IS NULL THEN NULL
                    ELSE '&agent_id=' || TO_CHAR(p_agent_id) END
            || '&as_of=' || UTL_URL.escape(TO_CHAR(p_as_of, c_date_fmt), TRUE),
            'GET');
        RETURN JSON_VALUE(l_reply, '$.rate_id' RETURNING NUMBER);
    END resolve_rate;

    PROCEDURE calculate_policy_commission (
        p_policy_id    IN policies.policy_id%TYPE,
        p_period_month IN VARCHAR2,
        p_actor        IN VARCHAR2
    ) IS
        l_body  VARCHAR2(4000);
        l_reply CLOB;
    BEGIN
        SELECT JSON_OBJECT(
                   'period_month' VALUE p_period_month,
                   'actor'        VALUE p_actor
                   NULL ON NULL)
          INTO l_body
          FROM dual;
        l_reply := call_service(
            '/policies/' || p_policy_id || '/commission', 'POST', l_body);
    END calculate_policy_commission;

END commission_pkg;
/

EXIT;
