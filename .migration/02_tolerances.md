# 02 — Reconciliation tolerances

Version: `1.0` (approved at STOP A, 2026-09-01)
Approval state: APPROVED — all rows below confirmed as proposed

| Surface | Proposed contract | Status |
|---|---|---|
| Recon mode | LIVE dual-connection source-to-target comparisons | PROPOSED |
| `NUMBER(p,0)`, `p <= 9` | BSON int; exact equality | PROPOSED |
| `NUMBER(p,0)`, `9 < p <= 18` | BSON long; exact equality | PROPOSED |
| `NUMBER` scaled, unbounded, or `p > 18` | Decimal128; half-even canonicalization; numeric tolerance 0 | PROPOSED |
| FLOAT / BINARY_FLOAT / BINARY_DOUBLE | BSON double; exact canonicalized equality | PROPOSED |
| Oracle DATE | Source session interpreted as UTC; BSON date; truncate to ms | PROPOSED |
| TIMESTAMP variants | Normalize to UTC, truncate to ms; TZ retention is a per-field mapping decision at STOP B | PROPOSED |
| Empty Oracle string (`'' IS NULL`) | Store explicit BSON `null` | PROPOSED |
| NULL vs missing field | Distinct; source NULL → explicit BSON `null`; missing means "column absent from mapping" | PROPOSED |
| CHAR blank padding | Right-strip before load and before comparison | PROPOSED |
| String collation | Binary, case-sensitive, unless census finds NLS case-insensitive paths | PROPOSED |
| Row/document counts | Zero difference | PROPOSED |
| Embedded array cardinality | Zero difference through approved mapping rules (incl. declared orphan policy) | PROPOSED |
| Per-field aggregates | Zero absolute and relative difference after canonicalization | PROPOSED |
| Full keyed diff threshold | Full diff up to 100,000 root documents per unit | PROPOSED |
| Above threshold | Full aggregates + deterministic stratified sample of 1,000 keys | PROPOSED |
| Known INVOICE_LINE orphans (37) | Quarantined with reason class `orphan_fk`, counted and dispositioned at STOP B; never silently dropped | PROPOSED |
| Quarantine policy | No silent drops; zero unresolved mismatches required for PASS | PROPOSED |
| Source-load cap | 1 concurrent Oracle extract/recon query | PROPOSED |
| Full pipeline re-run cap | 3 per unit, then halt and escalate | PROPOSED |
| Circuit breaker | 3 same-class failures across units halts the wave | FACT (org guardrail) |
| Parallel-run target | 3 consecutive green cycles, or explicit STOP C risk acceptance | PROPOSED |

## Evidence-integrity rules

- Every gate declares its source and target population, namespace, watermark, and seed.
- A child never reconciles against data it generated itself.
- Tier 1 counts through the mapping; embedded child rows are never hidden by root counts.
- Tier 2 aggregates are computed natively on both systems over the same population.
- Tier 3 uses stable keys; every embedded array declares element keys and graded fields —
  any UNGRADED embed is work, not a PASS.
- Tier 4 replays recorded representative application operations against both stacks.
- Harness `result.json` is the merge authority; no accelerator or manual check PASSes a unit.

## Amendment procedure

After STOP A approval, a tolerance changes only by explicit user approval recorded in
`05_decisions.md` as a new dated version, identifying every merged wave that requires
re-verification under the new version.
