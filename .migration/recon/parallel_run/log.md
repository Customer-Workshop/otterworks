# Phase 4 parallel-run evidence

The Oracle source fixture was frozen and idle throughout all three serial
reconciliation cycles. No live writes occurred during the validation window.
All target reads used `ow_tp_mongodb_032752` and its quarantine database.

| Cycle | Unit | Verdict | Result generated |
|---|---|---|---|
| cycle1 | U0 | DRIFT-EXPLAINED (approved) | 2026-09-01T18:01:12.827867+00:00 |
| cycle1 | U1 | PASS | 2026-09-01T18:03:19.291200+00:00 |
| cycle1 | U2 | PASS | 2026-09-01T18:03:48.135142+00:00 |
| cycle1 | U3 | PASS | 2026-09-01T18:03:51.566346+00:00 |
| cycle1 | U4 | PASS | 2026-09-01T18:03:55.165839+00:00 |
| cycle1 | U5 | PASS | 2026-09-01T18:03:58.303171+00:00 |
| cycle1 | U6 | PASS | 2026-09-01T18:04:01.077371+00:00 |
| cycle1 | U7 | PASS | 2026-09-01T18:04:02.908524+00:00 |
| cycle2 | U0 | DRIFT-EXPLAINED (approved) | 2026-09-01T18:04:17.686053+00:00 |
| cycle2 | U1 | PASS | 2026-09-01T18:05:29.155704+00:00 |
| cycle2 | U2 | PASS | 2026-09-01T18:05:55.516441+00:00 |
| cycle2 | U3 | PASS | 2026-09-01T18:05:58.654520+00:00 |
| cycle2 | U4 | PASS | 2026-09-01T18:06:03.196253+00:00 |
| cycle2 | U5 | PASS | 2026-09-01T18:06:06.166651+00:00 |
| cycle2 | U6 | PASS | 2026-09-01T18:06:09.151595+00:00 |
| cycle2 | U7 | PASS | 2026-09-01T18:06:10.829911+00:00 |
| cycle3 | U0 | DRIFT-EXPLAINED (approved) | 2026-09-01T18:06:14.295850+00:00 |
| cycle3 | U1 | PASS | 2026-09-01T18:07:25.941215+00:00 |
| cycle3 | U2 | PASS | 2026-09-01T18:07:52.285370+00:00 |
| cycle3 | U3 | PASS | 2026-09-01T18:07:55.752280+00:00 |
| cycle3 | U4 | PASS | 2026-09-01T18:07:59.330426+00:00 |
| cycle3 | U5 | PASS | 2026-09-01T18:08:02.490262+00:00 |
| cycle3 | U6 | PASS | 2026-09-01T18:08:05.296678+00:00 |
| cycle3 | U7 | PASS | 2026-09-01T18:08:07.008861+00:00 |

U0's raw harness result is `FAIL` in each cycle only because the approved
`fixture_meta.INITIALIZED_AT` count-only/declared-unexercised amendment is not
honored by the harness keyed-diff implementation. Each cycle had exactly the
approved `fixture_meta` timestamp missing/extra pair and no other findings.
