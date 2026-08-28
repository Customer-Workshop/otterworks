# 04 — Dependency register

## D1–D10 taxonomy

| ID | Category |
|---|---|
| D1 | Source/data availability |
| D2 | Schema/metadata |
| D3 | Transformation semantics |
| D4 | Consumer/reader coverage |
| D5 | Target/platform capability |
| D6 | Security/identity |
| D7 | Orchestration/operations |
| D8 | Data quality/reconciliation |
| D9 | Retention/cutover |
| D10 | External approval/access |

## Known items

### D10-1 — CLOSED

**FACT:** targeted `SELECT` grants, rather than `SELECT_CATALOG_ROLE`, were applied in
`FREEPDB1` and verified as `OW_BILLING`:

```sql
GRANT SELECT ON SYS.V_$SQL                     TO OW_BILLING;
GRANT SELECT ON SYS.V_$ACTIVE_SESSION_HISTORY  TO OW_BILLING;
GRANT SELECT ON AUDSYS.UNIFIED_AUDIT_TRAIL     TO OW_BILLING;
```

Observed counts after the grants:

- `SYS.V_$SQL`: `524`
- `SYS.V_$ACTIVE_SESSION_HISTORY`: `18`
- `AUDSYS.UNIFIED_AUDIT_TRAIL`: `13,894`

All three surfaces previously returned `ORA-00942`. AWR was deliberately not granted;
`dba_hist_sqlstat` returned `0` even as SYSDBA. Source: the settled intake
(`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:178-194`) and
the access evidence in `.migration/07_access_checklist.md`.

### D4-1 — OPEN / accepted

**FACT:** the customer declared the consumer population `UNMAPPED`; artifact-derived
known consumers do not prove complete reader coverage
(`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:157-159,169-176`).

### D4-2 — CLOSED-BY-DECISION

**FACT:** the customer declined an audit-trail observation window and accepted the
unmapped-consumer risk (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:160,196-224`).

No other dependency items are seeded here. A future blocked access probe must add a
new D10 item with an approver, exact permission, and command or console path.
