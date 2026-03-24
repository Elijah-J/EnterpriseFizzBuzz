import { useReducedMotion } from "@/lib/hooks/use-reduced-motion";

type ProgressVariant = "determinate" | "indeterminate";

interface ProgressBarProps {
  /** Current progress as a percentage (0-100). Used in determinate mode. */
  value?: number;
  /** Visual mode: determinate shows exact progress, indeterminate shows a shimmer sweep. */
  variant?: ProgressVariant;
  /** Optional label displayed above the progress bar. */
  label?: string;
  /** Accessible description of the progress state. */
  "aria-label"?: string;
}

/**
 * Horizontal progress indicator for long-running operations in the
 * Enterprise FizzBuzz Operations Center.
 *
 * The determinate variant renders an amber gradient fill that transitions
 * smoothly via CSS as the percentage value changes. The indeterminate
 * variant displays a shimmer sweep animation for operations with unknown
 * completion time, such as quantum evaluation initialization or neural
 * network weight calibration.
 *
 * Both variants respect the user's reduced-motion preferences.
 */
export function ProgressBar({
  value = 0,
  variant = "determinate",
  label,
  "aria-label": ariaLabel,
}: ProgressBarProps) {
  const reducedMotion = useReducedMotion();
  const clampedValue = Math.max(0, Math.min(100, value));

  return (
    <div className="w-full">
      {label && (
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs text-text-secondary">{label}</span>
          {variant === "determinate" && (
            <span className="text-xs font-mono text-text-muted">
              {Math.round(clampedValue)}%
            </span>
          )}
        </div>
      )}
      <div
        className="h-2 w-full rounded-full bg-surface-raised overflow-hidden"
        role="progressbar"
        aria-valuenow={variant === "determinate" ? clampedValue : undefined}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={ariaLabel ?? label}
      >
        {variant === "determinate" ? (
          <div
            className="h-full rounded-full transition-[width] duration-300 ease-out"
            style={{
              width: `${clampedValue}%`,
              background: "linear-gradient(90deg, var(--accent), var(--fizzbuzz-gold-light, var(--accent-hover)))",
            }}
          />
        ) : (
          <div
            className="h-full w-full rounded-full"
            style={{
              background: reducedMotion
                ? "var(--accent)"
                : "linear-gradient(90deg, transparent 0%, var(--accent) 50%, transparent 100%)",
              backgroundSize: reducedMotion ? "100% 100%" : "200% 100%",
              animation: reducedMotion
                ? "none"
                : "shimmer 1.8s ease-in-out infinite",
            }}
          />
        )}
      </div>
    </div>
  );
}
