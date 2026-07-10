# Playbook: Modernize an Oracle Forms Screen to a Verified REST Service

> **Facilitator / author:** this file is the source for a **Devin Playbook**.
> Copy its contents into your Devin organization (Settings → Playbooks → *Create
> a new Playbook*) so sessions can invoke it as `!modernize-oracle-forms`. See
> [Creating Playbooks](https://docs.devin.ai/product-guides/creating-playbooks).

## Overview

Use this playbook to modernize a legacy **Oracle Forms** module (`.fmb`, usually
exported to XML) into a modern **REST service** (Spring Boot 3 / Java 21 by
default), reproducing the form's behavior exactly and **proving** it with a
programmatic contract-parity harness — not by eyeballing the screen.

The trap in Forms modernization is that the interesting logic is not in the
column types; it lives in **triggers** — `WHEN-VALIDATE-ITEM`,
`WHEN-VALIDATE-RECORD`, `PRE-INSERT`, `POST-QUERY` — and in **LOVs / record
groups**. A rewrite that only maps tables and fields will silently drop
business rules. This playbook treats the Forms definition as the source of
truth and gates every endpoint on a test that encodes a specific Forms rule.

The guiding principle: **a converted endpoint is done when the contract-parity
harness is green — every Forms trigger reproduced as a machine-checkable
assertion — not when the code compiles or the screen "looks the same."**

## Required from user

- **The Forms module** — the `.fmb`/XML export (and, if available, the extracted
  trigger bodies and the underlying schema). This is the source of truth.
- **The target stack** — default Spring Boot 3 / Java 21 REST; state it if
  different.
- **The contract** — an OpenAPI (or equivalent) contract for the target API,
  distilled from the Forms blocks/items/triggers. If it does not exist yet,
  produce it first: it is what the harness asserts against.
- **The namespace** — the isolated branch for this run (e.g.
  `modernize/customers-block`) so concurrent runs never collide.

## Procedure

1. **Orient over the Forms module.** Enumerate the blocks (and their base
   tables), the items (data type, `Required`, `Maximum_Length`, `LOV`,
   `Format_Mask`, ranges), the LOVs / record groups (allowed value sets), and —
   most importantly — every trigger and the business rule it encodes. Produce a
   short rule inventory before writing code.
2. **Map each Forms construct to its REST equivalent.** Block → resource +
   endpoints; item property → request/response field + field validation; LOV →
   enum or referential check; `WHEN-VALIDATE-ITEM` / `-RECORD` → server-side
   validation returning `400` with the trigger's message; `PRE-INSERT` /
   `PRE-UPDATE` → pre-persist checks. Flag **cross-field** rules explicitly —
   they are the ones a naive conversion drops.
3. **Implement one block/endpoint group at a time** on the run's namespace
   branch. Reproduce the rules faithfully; do not "improve" or silently fix a
   quirk — flag it instead.
4. **Run the contract-parity harness.** It boots the service and asserts, per
   endpoint: existence and schema, field validations, LOV/enum constraints, and
   each trigger-derived rule (including cross-field ones), plus the persisted
   result.
5. **Fix failures against the source of truth and re-run.** When the harness is
   red, read which Forms rule the failing test cites, correct the implementation
   to match the trigger, and re-run until green. Never weaken the test to pass.
6. **Open a PR** with the implementation, the green harness report in the
   description, and a reference to the Forms module and contract. Keep the work
   on the namespace branch; do not merge the answer into the durable scaffold.

## Specifications (postconditions)

A conversion is complete when:

- [ ] Every block/item/trigger in scope has a corresponding assertion in the harness
- [ ] The contract-parity harness is **all green** against the running service
- [ ] Cross-field trigger rules (plan-dependent caps, parent-state checks, etc.)
      are enforced server-side, not just field ranges
- [ ] LOV / record-group value sets are enforced (enum or referential check)
- [ ] Validation errors return the correct HTTP status and the Forms message
- [ ] The work is on a namespace branch; the durable scaffold on `main` is untouched
- [ ] A PR is open with the green harness report and links to the Forms source

## Worked example: the dropped cross-field trigger

The `SUBSCRIPTIONS.DISCOUNT_PCT` item carries a `Format_Mask` and a
`Lowest/Highest_Allowed_Value` of `0..100`, **and** a `WHEN-VALIDATE-ITEM`
trigger that caps the discount at the plan's `MAX_DISCOUNT_PCT` — which is `0`
for every plan except `ENTERPRISE`:

```plsql
SELECT MAX_DISCOUNT_PCT INTO v_max_discount
  FROM STORAGE_PLANS WHERE PLAN_CODE = :SUBSCRIPTIONS.PLAN_CODE;
IF NVL(:SUBSCRIPTIONS.DISCOUNT_PCT, 0) > v_max_discount THEN
  FND_MESSAGE.SET_STRING('Discount exceeds plan maximum');
  RAISE FORM_TRIGGER_FAILURE;
END IF;
```

A plausible conversion maps the field range (`0..100`) and stops there, so a
15% discount on a `PRO` plan is accepted:

```
test_subscription_discount_over_plan_max_400  FAILED
  discount above the plan maximum must be rejected; a field-only 0..100
  range check would return 201. Got 201: {"planCode":"PRO","discountPct":15,...}
```

The fix looks up the plan and enforces the plan-dependent cap:

```java
if (discount.compareTo(plan.getMaxDiscountPct()) > 0) {
  throw new ValidationException("discountPct", "Discount exceeds plan maximum");
}
```

Re-run and it goes green. The point: "compiles and the form looks the same"
review would have shipped a rule the business depends on (enterprise-only
discounting). The harness caught it because the rule was encoded as an
assertion tied to the trigger.

## Advice

- Build the **rule inventory first** (one line per trigger/LOV). It becomes the
  test list and prevents silently dropping a rule.
- Cross-field and parent-state rules (a value validated against another table or
  the parent record) are where naive conversions fail — give them their own
  tests.
- Reproduce quirks faithfully; if a Forms rule looks wrong, flag it in the PR
  rather than "fixing" it. Redesign is a separate, deliberate decision.
- Keep the harness black-box (HTTP against the running service) so it is
  independent of the implementation's internal structure.
- Parallelize per block/endpoint group with child sessions; each on its own
  namespace branch, each producing its own verified PR.

## Forbidden actions

- Do **not** merge the implemented answer into the durable scaffold branch —
  `main` stays an unimplemented scaffold so the exercise repeats.
- Do **not** weaken, skip, or delete a harness assertion to make it pass.
- Do **not** silently "fix" or omit a Forms business rule — reproduce it or flag it.
- Do **not** hardcode credentials; read DB settings from environment/profiles.
- Do **not** claim done until the contract-parity harness is fully green.
