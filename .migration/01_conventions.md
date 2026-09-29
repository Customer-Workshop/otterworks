# 01 Conventions

- Migration writes go only to database `ow_tp_mmp_live` on Atlas cluster `otterworks-demo`
  (allowlist: `allowed_targets.json`). Quarantine is a collection inside that database
  (`quarantine_*`), never a second database.
- Branches: `migrate/billing/<wave>-<unit>` (setup is `migrate/billing/0-setup`), cut from and
  PR'd into `tp-run/mongodb-20260929T160602Z`. Never `tech-partnerships` or `main`.
- One PR per unit. PR body: Decisions, Code, Evidence; unverified paths first; under 2,000
  characters; `recon.summary.md` rendered, raw JSON linked.
- Merges: hard mode, so PASS PRs are held and merged after the wave-close reply.
- Secrets by name only (`OW_TP_ORACLE_RO_DSN`, `OW_TP_MMP_TARGET_URI`, `OW_TP_ORACLE_APP_PASSWORD`).
- Every PR passes `make tp-smoke`; recon JSON passes `make tp-validate-recon`.
- Recon artifacts: `.migration/recon/<unit>/`; wave files: `.migration/waves/wave-<N>.*`.
- Unrelated working-tree files (auth-service `.settings`, notification-service gradle wrapper,
  `bin/`) are never staged.
