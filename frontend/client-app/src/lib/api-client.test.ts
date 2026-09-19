import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { billingServer } from "@/test-setup";
import { createRawApiClient } from "./api-client";

describe("createRawApiClient", () => {
  it("preserves legacy keys containing digits", async () => {
    billingServer.use(
      http.get("/api/v1/billing/customer", () =>
        HttpResponse.json({
          udf_01: "legacy-value",
          addr_line_1: "123 Main Street",
        }),
      ),
    );

    const response = await createRawApiClient().get("/billing/customer");

    expect(response.data).toEqual({
      udf_01: "legacy-value",
      addr_line_1: "123 Main Street",
    });
  });
});
