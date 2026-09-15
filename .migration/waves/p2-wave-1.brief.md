# Pipeline 2, wave 1 close — PASS: `p2-sftp-ingest` landed, bronze built, official live recon green

Landed: 1 of 1 batch, 1 of 1 unit (`p2-sftp-ingest`). Failed: none. Blocked: none. Circuit breaker: 0 of 3.

What the unit replaces: `etl/legacy-extra/jobs/sftp_ingest_poll.ksh`. `CUSTBILL*.dat` now lands in `/Volumes/ow_tp/bronze/landing/custbill/` through a staged write plus atomic rename, and a Lakeflow Spark Declarative Pipeline builds `ow_tp.bronze.custbill_raw` (one row per physical record, raw bytes preserved, `HDR`/`TRL` kept so the wave-2 parser applies the legacy `sed` deletion itself) and the `ow_tp.bronze.custbill_files` ledger.

**Behaviour changes, named here and not only in a recon JSON:**
- **P2-D01 — the target cannot parse a half-written file; the legacy can.** Landing is atomic, so the target never sees a partial `.dat`. The differing case cannot be exercised against pinned inputs, so parity is proven only for whole files. Accepted at STOP C; repeated in the STOP E packet. The atomic PUT only covers the destination: the landing task also requires the source to be unchanged across a one-second window that spans the read (stat, wait, read, stat) and leaves anything that moved for the next run, so a growing file is never published as a complete one. Neither check is a handshake — a producer that pauses longer than the stability window defeats the legacy's 1-second double-stat and this one alike. Only an upstream rename-on-complete protocol closes it, which is D3-01 at STOP E.
- No source file is ever deleted. The legacy poller copied to `archive/` and then `rm`'d the source, swallowing failures; the ledger replaces the archive copy and nothing is removed.
- A same-name file whose bytes differ from the landed copy is a conflict and stops the landing; a byte-identical file is a no-op. Identity is the sha256 of the content, not the length, so an in-place correction of the same length is caught rather than skipped. The legacy overwrote silently.

Recon: official harness verdict **PASS**, `merge_eligible=true`, live, depth full, mapping `map-p2-v1`, tolerances `v1` — 123 records over 5 files, tier 3 keyed diff on `(source_file, record_no)` with zero findings. The source side is the captured legacy baseline loaded independently into `ow_tp.bronze.custbill_legacy_baseline_raw`, not the pipeline's own output. Report: `.migration/recon/p2-sftp-ingest/p2-sftp-ingest.recon.json`, harness output alongside it.

Idempotency was proven by an actual rerun, not inferred: landing rerun (6 files skipped, 0 conflicts) plus a second pipeline update left `custbill_raw` byte-identical — 123 rows, 7822 record bytes, content md5 `0b26fec48c3c75d5569194902469cc00` before and after (`idempotency.before.json`, `idempotency.after.json`).

**What this recon does not cover** (also listed in the recon report): the SFTP hop itself — the unit reconciles what is in the landing volume, and the `CB77340` drop stays out of scope until D3-01 at STOP E; structure parity — the harness compares rows, not table properties, grants or comments; and `source_principal_read_only`, still unverified because the doctor has no privilege query for a Databricks-family source.

One implementation note worth carrying: a zero-byte `.dat` is dropped by every Spark file reader before a task sees it, and `LIST` is refused inside a pipeline query definition, so the ledger enumerates the volume directory directly. The empty file therefore appears with `record_count 0` instead of vanishing — the legacy poller copied it and the legacy parser ran on it, so its arrival is a fact the ledger has to keep.

Base: `7af7a13b` on the working branch (pipeline 1 merged). Wave 0 (PR #1599) is still awaiting merge, so `databricks/migration/p2/recon/canonicalization.files.json` and the wave manifests referenced above arrive with that PR, not this one. Next: wave 2 `p2-custbill-parse`.
