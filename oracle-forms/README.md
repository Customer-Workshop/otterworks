# Oracle Forms Modernization — OtterWorks Storage Billing

A self-contained modernization use case: take a legacy **Oracle Forms** module
(`BILLING.fmb`) and rebuild it as a modern **Spring Boot 3 (Java 21) REST
service**, proving behavioral parity with a **programmatic contract harness**.

The point of the exercise is the verification loop: a modern rewrite is only
trustworthy if it reproduces the legacy business rules — and in Oracle Forms
those rules live in **triggers** (`WHEN-VALIDATE-ITEM`, `WHEN-VALIDATE-RECORD`,
`PRE-INSERT`), not just column types. The harness encodes each rule and gates
every change.

## Layout

| Path | Role |
|---|---|
| `legacy/BILLING.fmb.xml` | The Oracle Forms module export (source of truth): blocks, items, LOVs, triggers |
| `legacy/triggers/*.plsql` | The extracted PL/SQL trigger bodies, one per rule |
| `legacy/schema/legacy_schema.sql` | The legacy Oracle DDL |
| `contracts/openapi.yaml` | REST contract distilled from the Forms definition |
| `spring-boot-app/` | The modern target. `main` ships an empty scaffold (endpoints return 501) |
| `verify/` | Python contract-parity harness (pytest) run against the running service |

## Quick Start

```bash
make forms-verify     # boot the service (H2, in-memory) + run the harness + tear down
```

On `main` the service is an unimplemented scaffold, so the harness is red
(only `/health` passes). Implementing the business logic in
`spring-boot-app/src/main/java/com/otterworks/billing/service/BillingService.java`
turns it green.

```bash
make forms-build      # build the jar
make forms-run        # run on http://localhost:8092 (H2)
make forms-clean      # remove build artifacts
```

Prerequisites: Java 21 (the Gradle wrapper builds the app), Python 3 with
`oracle-forms/verify/requirements.txt` installed.

## The verification loop (and the bug it catches)

Each test in `verify/test_contract.py` cites the Forms artifact it proves. The
headline case is a **cross-field** rule: `SUBSCRIPTIONS.DISCOUNT_PCT` has a
`WHEN-VALIDATE-ITEM` trigger capping the discount at the plan's
`MAX_DISCOUNT_PCT` (0 for every plan except `ENTERPRISE`). A plausible
conversion reads the Forms `Format_Mask`/range (`0..100`) and stops there — so a
15% discount on a `PRO` plan returns `201` when it should return `400`. The
harness catches the wrong `201`; the fix is to look up the plan and enforce the
plan-dependent cap. See `legacy/triggers/SUBSCRIPTIONS-WVI-DISCOUNT_PCT.plsql`.
