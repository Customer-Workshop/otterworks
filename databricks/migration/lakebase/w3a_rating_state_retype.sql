-- D-010 correction for billing.rating_state.updated_at (wave 3 batch a, owner-directed).
--
-- rating_state is wave-0 DDL (w0a_pkg_ow_util.sql:168-178) and a runtime write for this batch,
-- so this file exists instead of an edit there: it is the one column D-010 missed when the six
-- mapping specs were re-typed. Oracle TIMESTAMP records no zone, so the Postgres target is
-- timestamp, never timestamptz - and this column is the pkg_rating -> pkg_invoicing hand-off
-- that wave 4 reads, so a zone-aware value here would spread to the invoicing side.
--
-- Safe to re-run and safe to run late: the statement is a no-op once the type matches, and the
-- table is write-empty until pkg_rating lands (p1-pkg-rating is BLOCKED on usage_events), so
-- there is no stored value to reinterpret. The precision follows Oracle's default 6, matching
-- rating_results.created_at.
--
-- The default moves with the type, for the same reason wave 0 used localtimestamp on
-- billing_audit_log.logged_at (w0a_pkg_ow_util.sql:122): now() is timestamptz, so leaving it in
-- place would convert through whatever TimeZone the writing session happens to carry. The
-- declared UTC assumption (plan decision P1-D3) is unchanged.
--
-- Nothing else on rating_state changes: same columns, same order, same primary key, same
-- NOT NULL and boolean default. The shape wave 0 pinned for w3-b still holds.

ALTER TABLE billing.rating_state
    ALTER COLUMN updated_at TYPE timestamp(6),
    ALTER COLUMN updated_at SET DEFAULT localtimestamp;
