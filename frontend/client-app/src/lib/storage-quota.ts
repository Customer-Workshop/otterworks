import type { StorageQuota } from "@/types";

/** Usage at or above this percentage of the tier's quota triggers the warning banner. */
export const STORAGE_WARNING_THRESHOLD = 90;

/** sessionStorage key recording that the user dismissed the banner this session. */
export const STORAGE_BANNER_DISMISSED_KEY = "otter_storage_banner_dismissed";

/**
 * Whether the storage warning banner should be shown.
 *
 * The threshold is evaluated against `usagePercentage`, which the backend computes
 * as used_bytes / quota_bytes — so it respects each subscription tier's quota_bytes
 * (a pro user's 90% is 180 GB; a free user's is 4.5 GB).
 */
export function shouldShowStorageBanner(
  quota: Pick<StorageQuota, "usagePercentage"> | null | undefined,
  dismissed: boolean,
): boolean {
  if (dismissed) return false;
  if (!quota) return false;
  const pct = Number(quota.usagePercentage);
  if (!Number.isFinite(pct)) return false;
  return pct >= STORAGE_WARNING_THRESHOLD;
}

/** Read the per-session dismissal flag (defaults to not-dismissed if unavailable). */
export function isStorageBannerDismissed(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.sessionStorage.getItem(STORAGE_BANNER_DISMISSED_KEY) === "true";
  } catch {
    return false;
  }
}

/** Persist the dismissal for the remainder of the browser session. */
export function dismissStorageBanner(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(STORAGE_BANNER_DISMISSED_KEY, "true");
  } catch {
    /* ignore storage failures — banner will simply reappear next load */
  }
}
