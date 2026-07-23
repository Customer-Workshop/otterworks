import { describe, it, expect } from "vitest";
import {
  shouldShowStorageBanner,
  STORAGE_WARNING_THRESHOLD,
} from "./storage-quota";

const q = (usagePercentage: number) => ({ usagePercentage });

describe("shouldShowStorageBanner", () => {
  it("uses a 90% threshold", () => {
    expect(STORAGE_WARNING_THRESHOLD).toBe(90);
  });

  it("shows the banner when usage is above 90% (AC-01)", () => {
    expect(shouldShowStorageBanner(q(95), false)).toBe(true);
  });

  it("shows the banner exactly at the 90% boundary (inclusive)", () => {
    expect(shouldShowStorageBanner(q(90), false)).toBe(true);
  });

  it("hides the banner below 90% (AC-03)", () => {
    expect(shouldShowStorageBanner(q(89.9), false)).toBe(false);
    expect(shouldShowStorageBanner(q(10), false)).toBe(false);
  });

  it("stays hidden once dismissed regardless of usage (AC-02)", () => {
    expect(shouldShowStorageBanner(q(99), true)).toBe(false);
  });

  it("does not show without quota data (AC-07)", () => {
    expect(shouldShowStorageBanner(null, false)).toBe(false);
    expect(shouldShowStorageBanner(undefined, false)).toBe(false);
  });

  it("guards against non-finite percentages (AC-07)", () => {
    expect(shouldShowStorageBanner(q(NaN), false)).toBe(false);
  });

  it("is tier-independent: it only reads usagePercentage, which is computed per-tier (AC-05)", () => {
    // A pro user at 75% (150GB/200GB) must not warn even though 150GB > a free quota.
    expect(shouldShowStorageBanner(q(75), false)).toBe(false);
    // A pro user at 95% (190GB/200GB) must warn.
    expect(shouldShowStorageBanner(q(95), false)).toBe(true);
  });
});
