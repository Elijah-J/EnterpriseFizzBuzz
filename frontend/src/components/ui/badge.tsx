import type { HTMLAttributes } from "react";

type BadgeVariant = "success" | "warning" | "error" | "info";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const variantStyles: Record<BadgeVariant, string> = {
  success: "bg-fizz-950 text-fizz-400 border-fizz-800",
  warning: "bg-amber-950 text-amber-400 border-amber-800",
  error: "bg-red-950 text-red-400 border-red-800",
  info: "bg-buzz-950 text-buzz-400 border-buzz-800",
};

/**
 * Status indicator badge for operational state representation.
 * Badge variants map directly to the platform's severity taxonomy:
 *   - success: nominal operation
 *   - warning: degraded performance or pending compliance action
 *   - error: service disruption or SLA breach
 *   - info: informational, no action required
 */
export function Badge({
  variant = "info",
  className = "",
  children,
  ...props
}: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${variantStyles[variant]} ${className}`}
      {...props}
    >
      {children}
    </span>
  );
}
