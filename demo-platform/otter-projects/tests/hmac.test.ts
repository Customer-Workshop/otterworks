import { describe, expect, it } from "vitest";
import { signBody, verifySignature } from "@/lib/hmac";

describe("hmac", () => {
  it("signs with sha256= prefix and verifies", () => {
    const sig = signBody("{\"a\":1}", "s3cret");
    expect(sig).toMatch(/^sha256=[0-9a-f]{64}$/);
    expect(verifySignature("{\"a\":1}", sig, "s3cret")).toBe(true);
  });
  it("rejects wrong secret, tampered body, and missing header", () => {
    const sig = signBody("body", "s3cret");
    expect(verifySignature("body", sig, "other")).toBe(false);
    expect(verifySignature("body!", sig, "s3cret")).toBe(false);
    expect(verifySignature("body", null, "s3cret")).toBe(false);
    expect(verifySignature("body", "sha256=short", "s3cret")).toBe(false);
  });
});
