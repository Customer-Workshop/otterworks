export function BillingAlert({
  message,
  onDismiss,
  tone = "error",
}: Readonly<{
  message: string;
  onDismiss: () => void;
  tone?: "error" | "success" | "warning";
}>) {
  const colors =
    tone === "success"
      ? "border-green-200 bg-green-50 text-green-800"
      : tone === "warning"
        ? "border-yellow-200 bg-yellow-50 text-yellow-800"
      : "border-red-200 bg-red-50 text-red-800";
  return (
    <div
      role="alert"
      className={`flex items-center justify-between gap-3 rounded-lg border px-4 py-3 text-sm ${colors}`}
    >
      <span>{message}</span>
      <button
        type="button"
        aria-label="Dismiss error"
        onClick={onDismiss}
        className="rounded px-2 py-1 font-semibold hover:bg-red-100"
      >
        Dismiss
      </button>
    </div>
  );
}
