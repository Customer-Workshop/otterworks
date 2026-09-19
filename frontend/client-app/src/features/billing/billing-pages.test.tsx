import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BillingAccountPage from "./account-page";
import BillingInvoicesPage from "./invoices-page";
import BillingOverviewPage from "./overview-page";
import { billingApi, type Customer } from "./api";

vi.mock("./api", () => ({
  billingApi: {
    me: vi.fn(),
    usage: vi.fn(),
    listPlans: vi.fn(),
    changePlan: vi.fn(),
    invoices: vi.fn(),
    invoiceLines: vi.fn(),
    customer: vi.fn(),
  },
  isEstateUnavailable: (error: unknown) => Boolean((error as { status?: number })?.status && [502, 503, 504].includes((error as { status: number }).status)),
  errorDetail: (error: unknown) => (error as { detail?: string })?.detail,
}));
vi.mock("@/components/ui/notification-bell", () => ({
  NotificationBell: () => null,
}));

const mockedApi = vi.mocked(billingApi);

function renderPage(element: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{element}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const me = {
  tenant_id: "tenant-1",
  name: "OtterWorks Admin",
  status: "active",
  tax_exempt: "N",
  entitlement: [{
    tenant_id: "tenant-1",
    plan_code: "GROWTH",
    tier: "growth",
    monthly_fee: "149",
    included_units: "500",
    subscription_status: "active",
    effective_on: "2026-09-19",
  }],
  customer: {
    cust_no: "OW-ADMIN-0001",
    cust_name: "OtterWorks Admin",
    cur_bal_amt: "149",
    past_due_amt: "0",
    credit_hold_yn: "N",
  },
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Billing overview", () => {
  it("renders the current plan and customer balance", async () => {
    mockedApi.me.mockResolvedValue(me);
    mockedApi.usage.mockResolvedValue({ summary: [], rating: [], events: [] });
    renderPage(<BillingOverviewPage />);
    expect(await screen.findByText("GROWTH")).toBeInTheDocument();
    expect(screen.getByText("Current: $149")).toBeInTheDocument();
    expect(screen.getByText("Source: OW_BILLING legacy estate (Oracle)")).toBeInTheDocument();
  });

  it("shows the estate unavailable state", async () => {
    mockedApi.me.mockRejectedValue({ status: 503, detail: "Oracle is offline" });
    mockedApi.usage.mockResolvedValue({ summary: [], rating: [], events: [] });
    renderPage(<BillingOverviewPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Billing is temporarily unavailable");
    expect(screen.getByText("Oracle is offline")).toBeInTheDocument();
  });
});

describe("Billing invoices", () => {
  it("expands invoice lines when an invoice is clicked", async () => {
    mockedApi.invoices.mockResolvedValue([{
      invoice_id: "invoice-1",
      period_start: "2026-02-01",
      period_end: "2026-02-28",
      subtotal: "100",
      tax: "10",
      total: "110",
      status: "ISSUED",
    }]);
    mockedApi.invoiceLines.mockResolvedValue([{ line_type: "CHARGE", amount: "100" }]);
    renderPage(<BillingInvoicesPage />);
    fireEvent.click(await screen.findByText(/2026-02-01/));
    expect(await screen.findByText("Invoice lines")).toBeInTheDocument();
    expect(screen.getByText("CHARGE")).toBeInTheDocument();
  });
});

describe("Billing account", () => {
  it("renders all legacy fields and EAV rows", async () => {
    const customer = {
      ...Object.fromEntries(Array.from({ length: 155 }, (_, index) => [`field_${index}`, `value-${index}`])),
      attributes: [{ attr_name: "TAX_REGION_OVERRIDE", attr_value: "US", attr_type: "STRING" }],
    } as unknown as Customer;
    mockedApi.customer.mockResolvedValue(customer);
    renderPage(<BillingAccountPage />);
    expect(await screen.findByText("All 155 legacy fields")).toBeInTheDocument();
    fireEvent.click(screen.getByText("All 155 legacy fields"));
    await waitFor(() => expect(within(screen.getByText("All 155 legacy fields").closest("details") as HTMLElement).getAllByRole("row")).toHaveLength(155));
    expect(screen.getByText("TAX_REGION_OVERRIDE")).toBeInTheDocument();
  });
});
