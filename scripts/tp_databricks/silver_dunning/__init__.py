"""silver_dunning: the wave 4 unit of the OW_BILLING → Databricks run.

`pkg_dunning` (`fn_overdue_accounts`, `sp_schedule_dunning`, `sp_suspend_overdue`) and
`JOB_NIGHTLY_DUNNING` on Delta, plus the live reconciliation that measures the port against the
Oracle source, the pinned transcripts and the Delta targets. This is the estate's only unit that
writes a column on another unit's table (`ow_tp.silver.subscriptions`, wave 3's), so the shared-write
evidence is part of the recon rather than a footnote.
"""
