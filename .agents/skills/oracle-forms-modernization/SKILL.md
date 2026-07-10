---
name: oracle-forms-modernization
description: >
  Repo-specific mechanics for modernizing the legacy Oracle Forms "Storage
  Billing" module (oracle-forms/) into the Spring Boot billing service. Covers
  the Forms source layout, the trigger-to-rule mapping, the exact build/run/verify
  commands, and where to implement the business logic.
---

# Oracle Forms Modernization — OtterWorks

This skill provides the repo-specific mechanics the `!modernize-oracle-forms`
Playbook relies on. It is auto-loaded when Devin works in this repository.

## Where everything lives

| Path | Role |
|---|---|
| `oracle-forms/legacy/BILLING.fmb.xml` | Forms module export — SOURCE OF TRUTH (blocks, items, LOVs, triggers) |
| `oracle-forms/legacy/triggers/*.plsql` | Extracted PL/SQL trigger bodies, one per rule |
| `oracle-forms/legacy/schema/legacy_schema.sql` | Legacy Oracle DDL |
| `oracle-forms/contracts/openapi.yaml` | REST contract distilled from the Forms definition |
| `oracle-forms/spring-boot-app/` | Modern target (Spring Boot 3 / Java 21). `main` = empty scaffold |
| `oracle-forms/verify/test_contract.py` | Contract-parity harness (pytest, black-box HTTP) |

**Implement the business logic in exactly one place:**
`oracle-forms/spring-boot-app/src/main/java/com/otterworks/billing/service/BillingService.java`
— on `main` every method throws `NotImplementedException` (HTTP 501). The
controllers, DTOs, entities, repositories, exception handler, schema, and seed
data are already wired; the task is to fill in the service methods.

## Commands

```bash
make forms-build     # cd oracle-forms/spring-boot-app && ./gradlew bootJar
make forms-run       # run on http://localhost:8092 (H2, in-memory)
make forms-verify    # boot the service + run the contract-parity harness + tear down
make forms-clean     # remove build artifacts
```

`make forms-verify` is the loop: it builds the jar (if needed), starts it on
`FORMS_PORT` (default 8092), waits for `/health`, runs
`oracle-forms/verify/test_contract.py`, and stops the app. No Docker or external
DB — the default `h2` profile is in-memory and seeds the plans from
`src/main/resources/data.sql`.

Requires Java 21 (`run_contract.sh` finds it via `JAVA_HOME` or
`~/.sdkman/candidates/java/21*`) and the harness deps:
`pip install -r oracle-forms/verify/requirements.txt`.

## Trigger → REST rule mapping (the rule inventory)

| Forms artifact | Rule | REST behavior |
|---|---|---|
| `CUSTOMERS.CONTACT_EMAIL` WHEN-VALIDATE-ITEM | required, email-shaped, maxlen 120 | `400 {field: contactEmail}` |
| `CUSTOMERS.STATUS` LOV `STATUS_LOV` | ACTIVE\|SUSPENDED\|CLOSED, default ACTIVE | `400 {field: status}` |
| `SUBSCRIPTIONS.PLAN_CODE` LOV `PLAN_LOV` | must exist in `storage_plans` | `400 {field: planCode}` |
| `SUBSCRIPTIONS.SEATS` WHEN-VALIDATE-ITEM | `1 <= seats <= plan.maxSeats` (**cross-field**) | `400 {field: seats}` |
| `SUBSCRIPTIONS.DISCOUNT_PCT` WHEN-VALIDATE-ITEM | `0 <= discount <= plan.maxDiscountPct` (**cross-field**) | `400 {field: discountPct}` |
| `SUBSCRIPTIONS` WHEN-VALIDATE-RECORD | `endDate > startDate` when present | `400 {field: endDate}` |
| `SUBSCRIPTIONS` PRE-INSERT | parent customer not `CLOSED` | `400 {field: customerId}` |

The two **cross-field** rules (seats/discount vs. the plan) are the ones a
field-only conversion drops — they require a plan lookup. Validation errors use
the shape `{"field": "...", "message": "..."}` (see `dto/Dtos.ErrorResponse` and
`exception/GlobalExceptionHandler`).

## Reference data (seeded)

Plans in `storage_plans` (from `data.sql`) — the LOV source and the caps the
cross-field triggers validate against:

| planCode | maxSeats | maxDiscountPct |
|---|---|---|
| FREE | 1 | 0 |
| BASIC | 5 | 0 |
| PRO | 25 | 0 |
| ENTERPRISE | 500 | 20 |

## Namespacing / reverting

Do the work on a namespace branch (e.g. `modernize/subscriptions-block`); the
scaffold on `main` stays unimplemented so the exercise repeats. Revert is just
discarding the branch — `main` is untouched. To reset a local build:
`make forms-clean`.

## Answer key

A reference implementation of `BillingService` lives on the
`oracle-forms/answer-key` branch (not merged to `main`). Use it only to confirm
the harness after a run; do not copy it during the exercise.
