import type { HTMLAttributes } from "react";

type BadgeVariant = "success" | "warning" | "error" | "info";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const variantStyles: Record<BadgeVariant, string> = {
  success: "bg-fizz-400/15 text-fizz-400",
  warning: "bg-[var(--accent)]/15 text-[var(--accent)]",
  error: "bg-[var(--status-error)]/15 text-[var(--status-error)]",
  info: "bg-buzz-400/15 text-buzz-400",
};

/**
 * Status indicator badge for operational state representation.
 * Badge variants map directly to the platform's severity taxonomy:
 *   - success: nominal operation
 *   - warning: degraded performance or pending compliance action
 *   - error: service disruption or SLA breach
 *   - info: informational, no action required
 *
 * Backgrounds use domain color at 15% opacity for soft, confident presence
 * that integrates with the warm stone surface system without visual
 * aggression or attention-demanding effects.
 */
export function Badge({
  variant = "info",
  className = "",
  children,
  ...props
}: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${variantStyles[variant]} ${className}`}
      {...props}
    >
      {children}
    </span>
  );
}
