import { cn } from "@/lib/utils";

interface LoadingSpinnerProps {
  readonly size?: "sm" | "md" | "lg";
  readonly className?: string;
}

export function LoadingSpinner({ size = "md", className }: LoadingSpinnerProps): React.JSX.Element {
  const sizeClasses = {
    sm: "w-4 h-4 border-2",
    md: "w-8 h-8 border-3",
    lg: "w-12 h-12 border-4",
  };

  return (
    <div
      className={cn(
        "animate-spin rounded-full border-gray-200 border-t-otter-600",
        sizeClasses[size],
        className
      )}
      role="status"
      aria-label="Loading"
    />
  );
}

export function PageLoader(): React.JSX.Element {
  return (
    <div className="flex items-center justify-center min-h-[400px]">
      <LoadingSpinner size="lg" />
    </div>
  );
}
