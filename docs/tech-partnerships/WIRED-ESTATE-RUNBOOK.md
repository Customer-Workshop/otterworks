# Connected billing estate runbook

This runbook exercises the optional OtterWorks billing estate wiring. It is
estate integration work, not a migration unit: the normal golden application
path remains unchanged, and migration-only `ow_tp` prefixes do not apply.

## Start and stop

Start the connected core profile with a namespace:

```bash
make tp-up NS=demo PROFILE=core
```

The first Oracle boot can take several minutes while Oracle Database Free
starts and its completion-marker health check passes. The seed guard checks both
the namespace manifest and Oracle's `invoice_header` rows, so a stale manifest
does not suppress a needed seed.
Each Oracle boot also applies the idempotent static upgrade for the admin
tenant rows; applying it repeatedly leaves the row counts unchanged.

Run the asynchronous usage demonstration:

```bash
make tp-usage-demo NS=demo
```

Run the month-end batch and publish its report:

```bash
make tp-month-end NS=demo
```

Stop the wired application and infrastructure without deleting Oracle data:

```bash
make tp-down
```

`etl/legacy-extra/reports/` is generated output. The TP Compose bind mount
creates it when needed; it is ignored by Git and deliberately has no
`.gitkeep`.

The legacy billing and usage bridge ports are bound to loopback only
(`127.0.0.1:8096` and `127.0.0.1:8097`). The `/internal/usage/events` endpoint
and trusted identity headers are intended to be reached only from the Compose
network or through the API gateway. Override `USAGE_INTERNAL_TOKEN` outside a
local workstation instead of using the development default.

## What the screens show

### Storefront Billing overview

The Billing overview shows the signed-in tenant, current entitlement, customer
balance and credit-hold state, current-month usage summary, and recent usage
events. Requests go through the API gateway to `legacy-billing`, whose Oracle
backend calls the OW_BILLING PL/SQL package.

### Billing Plans

Plans are the Oracle plan catalog. The current plan is highlighted, and a
dated plan change submits through the same gateway and facade to the Oracle
subscription procedure.

### Billing Invoices

Invoices and expandable invoice lines come from the Oracle invoice facade. This
is the live invoice view, not the month-end finance batch.

### Billing Account

Account shows the legacy customer key fields, all preserved legacy columns
(including keys with digits), and EAV attributes from `customer_attributes`.
The source is the Oracle customer facade.

### Admin billing report

The admin report's overdue and dunning panels call the Oracle report SQL through
the admin facade. They require an admin identity and show the estate-unavailable
state when the gateway or Oracle is unavailable.

### Admin finance batch

The Month-end finance batch panel reads the persisted CSV produced by the
Oracle CUSTBILL extract and the existing ksh/Perl chain:

```text
Oracle invoices
  -> CUSTBILL fixed-width extract
  -> legacy-etl parse and ksh/Perl report
  -> finance CSV
  -> legacy-billing /api/reports/finance
  -> admin dashboard finance panel
```

It is explicitly batch-derived and is not a live Oracle query.

## Data paths and failure behavior

```text
Storefront Billing -> API gateway -> legacy-billing -> Oracle PL/SQL
Usage -> SNS/SQS -> usage-bridge -> Oracle USAGE_EVENTS
Admin billing report -> legacy-billing report SQL -> Oracle report queries
Finance panel -> Oracle CUSTBILL extract -> fixed-width parser -> ksh/Perl
  chain -> finance CSV -> legacy-billing finance endpoint -> admin dashboard
```

If Oracle is down, billing pages and report panels show an amber “Billing is
temporarily unavailable” state rather than inventing data. The usage bridge
does not block document or file operations: connection failures and 5xx
responses remain visible in SQS for visibility-timeout retry, while successful
recorded or duplicate responses are deleted. Unsupported events are skipped.

## Before-video recording checklist

Record the “before” flow in this order:

1. Show the normal OtterWorks landing page and sign in as `admin@otterworks.dev`.
2. Open Billing Overview and show the Oracle source caption, entitlement,
   balance, and usage section.
3. Open Plans, show the current plan, and show the effective-date change form
   without committing an unwanted change.
4. Open Invoices and expand an invoice line when the seeded namespace has one.
5. Open Account and scroll through key fields, the full legacy-field table, and
   EAV attributes.
6. Open the admin billing report and show overdue, dunning, and the Month-end
   finance batch source badge and totals.
7. If demonstrating operations, run `make tp-usage-demo NS=demo`, then refresh
   usage and show the new event.
8. Run `make tp-month-end NS=demo`, refresh the finance panel, and show that it
   is batch output.

Do not describe seeded records as a fixture or fake production system in the
audience-facing recording; describe the connected OW_BILLING legacy estate.

## Verification performed

Verified locally:

- Facade curls against the Oracle-backed legacy billing service.
- Usage bridge idempotency: first delivery recorded and exact redelivery
  reported duplicate.
- Two Oracle CUSTBILL extracts compared byte-for-byte with `cmp`.
- `make tp-smoke`.
- JSON contract validation with `make tp-validate-contracts`.

Not verified on this box:

- A complete `make tp-up NS=demo PROFILE=core`: host port 5432 was occupied,
  and the auth-service image build encountered Maven HTTP 403 responses.
- Browser screenshots of the storefront and admin pages.

## TP pre-PR self-check

This is estate wiring rather than a migration unit, so migration-specific
checks are recorded explicitly instead of being implied green.

| Checklist item | Status and evidence |
|---|---|
| NULL/missing attribution cannot fail open | **Verified** for bridge mapping and facade identity validation; unsupported or incomplete usage events are skipped. |
| Namespace and `ow_tp`/`ow-tp-` prefixes | **N/A**: this unit wires an existing estate; no migration catalog or target objects are created. |
| No shared-table DDL changes | **N/A**: no migration DDL is part of this wiring; Oracle is read/written through existing procedures and tables. |
| Rerun-safe retention and cleanup | **Verified** for month-end reruns and namespace-isolated reports; Oracle seed is guarded by actual rows. |
| Cleanup retains evidence | **N/A**: no destructive cleanup is performed by this unit. |
| No secrets/tokens/real distribution lists | **Verified** by branch-diff scans; only documented development defaults and `admin@otterworks.dev` are retained. |
| Parity/tolerance matches contract | **Verified** by the route, bridge, finance, and JSON contract baselines. |
| Idempotency proven by rerun | **Verified** by bridge duplicate delivery and extract `cmp`. |
| Recon recomputed from target platform | **N/A**: no migration reconciliation report is produced. |
| Every unverified path listed | **Verified**: full compose boot and browser screenshots are listed above. |
| Recon report kind/schema | **N/A**: this is not a migration unit and produces no recon report. |
| Capability preflight | **N/A**: no cloud capability or migration target is required. |
| `make tp-smoke` green | **Verified** locally with Go and Node toolchains loaded. |
