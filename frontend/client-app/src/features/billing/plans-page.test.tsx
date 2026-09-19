import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BillingPlansPage from "./plans-page";
import { billingApi } from "./api";

vi.mock("./api", () => ({
  billingApi: {
    me: vi.fn(),
    listPlans: vi.fn(),
    changePlan: vi.fn(),
  },
  isEstateUnavailable: (error: unknown) => [502, 503, 504].includes((error as { status?: number })?.status ?? 0),
  errorDetail: (error: unknown) => (error as { detail?: string })?.detail,
}));
vi.mock("@/components/ui/notification-bell", () => ({
  NotificationBell: () => null,
}));

const mockedApi = vi.mocked(billingApi);

beforeEach(() => {
  vi.stubEnv("VITE_ENABLE_BILLING", "true");
  vi.clearAllMocks();
  mockedApi.listPlans.mockResolvedValue([
    { plan_id: "starter", plan_code: "STARTER", tier: "starter", monthly_fee: "49", included_units: "100", overage_rate: "0.055" },
    { plan_id: "growth", plan_code: "GROWTH", tier: "growth", monthly_fee: "149", included_units: "500", overage_rate: "0.035" },
  ]);
  mockedApi.me.mockResolvedValue({
    tenant_id: "tenant-1",
    name: "OtterWorks Admin",
    status: "active",
    tax_exempt: "N",
    entitlement: [{
      tenant_id: "tenant-1",
      plan_code: "STARTER",
      tier: "starter",
      monthly_fee: "49",
      included_units: "100",
      subscription_status: "active",
      effective_on: "2026-09-19",
    }],
    customer: null,
  });
});

describe("Billing plans", () => {
  it("marks the current plan and posts a plan change", async () => {
    mockedApi.changePlan.mockResolvedValue({ status: "changed", entitlement: [] });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter><BillingPlansPage /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("button", { name: "Current plan" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Switch to this plan" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm change" }));
    expect(mockedApi.changePlan).toHaveBeenCalledWith("growth", expect.any(String));
    expect(await screen.findByRole("alert")).toHaveTextContent("Plan change saved");
  });

  it("shows a plan-change validation detail without hiding the catalog", async () => {
    mockedApi.changePlan.mockRejectedValue({ status: 400, detail: "effective_on must be today or later" });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter><BillingPlansPage /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("button", { name: "Current plan" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Switch to this plan" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm change" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("effective_on must be today or later");
    expect(screen.getByRole("heading", { name: "STARTER" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "GROWTH" })).toBeInTheDocument();
  });

  it("keeps the saved entitlement when the refresh fails", async () => {
    mockedApi.changePlan.mockResolvedValue({
      status: "changed",
      entitlement: [{
        tenant_id: "tenant-1",
        plan_code: "SCALE",
        tier: "scale",
        monthly_fee: "499",
        included_units: "2500",
        subscription_status: "active",
        effective_on: "2026-09-19",
      }],
    });
    mockedApi.me
      .mockResolvedValueOnce({
        tenant_id: "tenant-1",
        name: "OtterWorks Admin",
        status: "active",
        tax_exempt: "N",
        entitlement: [{
          tenant_id: "tenant-1",
          plan_code: "STARTER",
          tier: "starter",
          monthly_fee: "49",
          included_units: "100",
          subscription_status: "active",
          effective_on: "2026-09-19",
        }],
        customer: null,
      })
      .mockRejectedValueOnce(new Error("refresh failed"));
    mockedApi.listPlans.mockResolvedValue([
      { plan_id: "starter", plan_code: "STARTER", tier: "starter", monthly_fee: "49", included_units: "100", overage_rate: "0.055" },
      { plan_id: "scale", plan_code: "SCALE", tier: "scale", monthly_fee: "499", included_units: "2500", overage_rate: "0.025" },
    ]);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter><BillingPlansPage /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("button", { name: "Current plan" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Switch to this plan" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm change" }));
    expect(await screen.findByText("Plan change saved.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Current plan" })).toBeInTheDocument();
    expect(await screen.findByText("Plan change saved, but the account could not be refreshed.")).toBeInTheDocument();
    expect(screen.queryByText("Plan change was not accepted.")).not.toBeInTheDocument();
  });
});
