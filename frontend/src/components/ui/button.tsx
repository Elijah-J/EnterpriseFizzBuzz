"use client";

import { useRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { usePress } from "@/lib/hooks/use-press";

type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** When true, renders an animated loading indicator and disables interaction. */
  loading?: boolean;
  /** Optional icon element rendered before the button label. */
  icon?: ReactNode;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-text-inverse hover:bg-accent-hover focus-visible:ring-[var(--accent)]/50",
  secondary:
    "bg-surface-raised text-text-secondary border border-border-subtle hover:bg-surface-overlay focus-visible:ring-border-default",
  ghost:
    "bg-transparent text-text-muted hover:bg-surface-raised hover:text-text-secondary focus-visible:ring-border-default",
  destructive:
    "bg-[var(--status-error)] text-text-primary hover:opacity-90 focus-visible:ring-[var(--status-error)]/50",
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-xs gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
  lg: "h-12 px-6 text-base gap-2.5",
};

/**
 * Standard action trigger for the Enterprise FizzBuzz Operations Center.
 * All user-initiated state mutations must be routed through this component
 * to ensure consistent interaction patterns across the platform.
 *
 * Press interactions use spring-based scale animation via the usePress hook,
 * replacing static CSS active:scale transforms with physically-modeled
 * compression and overshoot recovery. The loading state renders three
 * sequentially animated dots to communicate pending operations without
 * the cognitive overhead of spinner animations.
 */
export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  icon,
  className = "",
  children,
  disabled,
  ...props
}: ButtonProps) {
  const buttonRef = useRef<HTMLButtonElement>(null);
  usePress(buttonRef);

  return (
    <button
      ref={buttonRef}
      data-cursor="pointer"
      className={`inline-flex items-center justify-center rounded font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-ground disabled:pointer-events-none disabled:opacity-50 ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <span
          role="status"
          className="inline-flex items-center gap-1"
          aria-label="Loading"
        >
          <span className="h-1 w-1 rounded-full bg-current animate-[loading-dot_1s_ease-in-out_infinite]" />
          <span className="h-1 w-1 rounded-full bg-current animate-[loading-dot_1s_ease-in-out_0.15s_infinite]" />
          <span className="h-1 w-1 rounded-full bg-current animate-[loading-dot_1s_ease-in-out_0.3s_infinite]" />
        </span>
      ) : (
        <>
          {icon && <span className="shrink-0">{icon}</span>}
          {children}
        </>
      )}
    </button>
  );
}
