import plansFixture from "./__fixtures__/plans.json";
import meFixture from "./__fixtures__/me.json";
import invoicesFixture from "./__fixtures__/invoices.json";
import { describe, expect, it } from "vitest";
import type { Invoice, Me, Plan } from "./api";

describe("billing facade fixtures", () => {
  it("matches the documented Plan, Me, and Invoice shapes", () => {
    const plan = plansFixture[0] as Plan;
    const me = meFixture as Me;
    const invoice = invoicesFixture[0] as Invoice;

    expect(Object.keys(plan)).toEqual([
      "plan_id",
      "plan_code",
      "tier",
      "monthly_fee",
      "included_units",
      "overage_rate",
    ]);
    expect(me).toMatchObject({
      tenant_id: expect.any(String),
      name: expect.any(String),
      status: expect.any(String),
      tax_exempt: expect.any(String),
      entitlement: expect.any(Array),
      customer: expect.objectContaining({ cust_no: expect.any(String) }),
    });
    expect(invoice).toMatchObject({
      invoice_id: expect.any(String),
      period_start: expect.any(String),
      period_end: expect.any(String),
      subtotal: expect.any(String),
      tax: expect.any(String),
      total: expect.any(String),
      status: expect.any(String),
    });
  });
});
