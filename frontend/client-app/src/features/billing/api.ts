import axios from "axios";
import { apiClient } from "@/lib/api-client";

export class BillingApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: string,
  ) {
    super(message);
  }
}

export type Plan = {
  plan_id: string;
  plan_code: string;
  tier: string;
  monthly_fee: string;
  included_units: string;
  overage_rate: string;
};

export type Entitlement = {
  tenant_id: string;
  plan_code: string;
  tier: string;
  monthly_fee: string;
  included_units: string;
  subscription_status: string;
  effective_on: string;
};

export type CustomerSummary = {
  cust_no: string;
  cust_name: string;
  cur_bal_amt: string;
  past_due_amt: string;
  credit_hold_yn: string;
};

export type Me = {
  tenant_id: string;
  name: string;
  status: string;
  tax_exempt: string;
  entitlement: Entitlement[];
  customer: CustomerSummary | null;
};

export type UsageEvent = {
  id: string;
  occurred_at: string;
  units: string;
  kind: string;
};

export type Usage = {
  summary: Array<Record<string, string | number | null>>;
  rating: Array<Record<string, string | number | null>>;
  events: UsageEvent[];
};

export type Invoice = {
  invoice_id: string;
  period_start: string;
  period_end: string;
  subtotal: string;
  tax: string;
  total: string;
  status: string;
};

export type CustomerAttribute = Record<string, string | number | null>;

export type Customer = {
  [key: string]: string | number | null | CustomerAttribute[];
  attributes: CustomerAttribute[];
};

function camelToSnake(key: string): string {
  return key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
}

function normalizeKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalizeKeys);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, child]) => [
        camelToSnake(key),
        normalizeKeys(child),
      ]),
    );
  }
  return value;
}

async function request<T>(
  path: string,
  config: { method?: "GET" | "POST"; params?: Record<string, string>; data?: unknown } = {},
): Promise<T> {
  try {
    const response = await apiClient.request({
      url: path,
      method: config.method ?? "GET",
      params: config.params,
      data: config.data,
    });
    return normalizeKeys(response.data) as T;
  } catch (error: unknown) {
    if (axios.isAxiosError(error)) {
      const status = error.response?.status ?? 0;
      const detail =
        typeof error.response?.data?.detail === "string"
          ? error.response.data.detail
          : undefined;
      throw new BillingApiError(
        detail ?? `Billing service returned ${status || "an unknown error"}`,
        status,
        detail,
      );
    }
    throw error;
  }
}

export function isEstateUnavailable(error: unknown): boolean {
  return error instanceof BillingApiError && [502, 503, 504].includes(error.status);
}

export function errorDetail(error: unknown): string | undefined {
  return error instanceof BillingApiError ? error.detail : undefined;
}

export const billingApi = {
  listPlans: () => request<Plan[]>("/billing/plans"),
  me: (on?: string) => request<Me>("/billing/me", { params: on ? { on } : undefined }),
  entitlement: (on: string) => request<Entitlement[]>("/billing/entitlement", { params: { on } }),
  changePlan: (planId: string, effectiveOn: string) =>
    request<{ status: string; entitlement: Entitlement[] }>("/billing/plan-change", {
      method: "POST",
      data: { plan_id: planId, effective_on: effectiveOn },
    }),
  usage: (periodStart: string, periodEnd: string) =>
    request<Usage>("/billing/usage", {
      params: { period_start: periodStart, period_end: periodEnd },
    }),
  invoices: () => request<Invoice[]>("/billing/invoices"),
  invoiceLines: (invoiceId: string) =>
    request<Array<Record<string, string | number | null>>>(
      `/billing/invoices/${encodeURIComponent(invoiceId)}/lines`,
    ),
  customer: () => request<Customer>("/billing/customer"),
};
