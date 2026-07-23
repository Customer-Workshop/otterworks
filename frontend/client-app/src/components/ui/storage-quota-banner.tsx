import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, X } from "lucide-react";
import { storageApi } from "@/lib/api";
import { formatFileSize } from "@/lib/utils";
import {
  shouldShowStorageBanner,
  isStorageBannerDismissed,
  dismissStorageBanner,
} from "@/lib/storage-quota";
import { useAuthStore } from "@/stores/auth-store";

/**
 * App-wide warning shown when the signed-in user is at/above 90% of their storage
 * quota. Dismissible for the remainder of the session; its action routes to Files
 * where the user can free space. Data comes from the real /storage/quota endpoint.
 */
export function StorageQuotaBanner() {
  const navigate = useNavigate();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const [dismissed, setDismissed] = useState(() => isStorageBannerDismissed());

  const { data: quota } = useQuery({
    queryKey: ["storage", "quota"],
    queryFn: () => storageApi.getQuota(),
    enabled: isAuthenticated && !dismissed,
    staleTime: 60_000,
  });

  if (!shouldShowStorageBanner(quota, dismissed) || !quota) return null;

  const handleDismiss = () => {
    dismissStorageBanner();
    setDismissed(true);
  };

  return (
    <div
      role="alert"
      className="mb-4 flex items-start gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-amber-900"
    >
      <AlertTriangle size={20} className="mt-0.5 flex-shrink-0 text-amber-600" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold">You&apos;re running low on storage</p>
        <p className="text-sm text-amber-800">
          You&apos;ve used {Math.round(quota.usagePercentage)}% of your storage
          {" "}({formatFileSize(quota.usedBytes)} of {formatFileSize(quota.quotaBytes)}).
          Free up space before you hit your limit.
        </p>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <button
          type="button"
          onClick={() => navigate("/files")}
          className="rounded-lg bg-amber-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-amber-700"
        >
          Manage storage
        </button>
        <button
          type="button"
          onClick={handleDismiss}
          aria-label="Dismiss storage warning"
          className="rounded-lg p-1.5 text-amber-600 transition hover:bg-amber-100"
        >
          <X size={18} />
        </button>
      </div>
    </div>
  );
}
