import type { HTMLAttributes } from "react";

type CardVariant = "default" | "elevated" | "featured";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Visual variant controlling surface elevation and accent treatment. */
  variant?: CardVariant;
}

const variantStyles: Record<CardVariant, string> = {
  default: "bg-surface-raised border-border-subtle",
  elevated: "bg-surface-overlay border-border-default",
  featured:
    "bg-surface-raised border-border-subtle border-l-2 border-l-[var(--accent)]",
};

/**
 * Primary container for operational data panels. Each Card represents
 * a discrete monitoring surface within the FizzBuzz Operations Center.
 *
 * Three elevation variants support the platform's layered depth system:
 * - `default`: Standard raised surface for general content panels
 * - `elevated`: Overlay surface with stronger border for modal-adjacent contexts
 * - `featured`: Amber left-border accent for primary KPI and hero metrics
 *
 * A grain overlay at 2% opacity is applied to all variants, providing the
 * editorial texture quality that distinguishes the Warm Precision design
 * language from flat digital rendering.
 */
export function Card({
  variant = "default",
  className = "",
  children,
  ...props
}: CardProps) {
  return (
    <div
      className={`relative rounded-lg border transition-colors overflow-hidden ${variantStyles[variant]} ${className}`}
      {...props}
    >
      {/* Grain overlay — editorial texture at imperceptible opacity */}
      <div
        className="absolute inset-0 pointer-events-none z-[1]"
        style={{
          backgroundImage: "var(--texture-grain)",
          backgroundRepeat: "repeat",
          opacity: 0.02,
        }}
      />
      <div className="relative z-[2]">{children}</div>
    </div>
  );
}

export function CardHeader({
  className = "",
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`border-b border-border-subtle px-4 py-3 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardContent({
  className = "",
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`px-4 py-3 ${className}`} {...props}>
      {children}
    </div>
  );
}

export function CardFooter({
  className = "",
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`border-t border-border-subtle px-4 py-3 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
