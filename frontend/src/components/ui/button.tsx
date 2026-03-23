import type { ButtonHTMLAttributes } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-fizzbuzz-600 text-white hover:bg-fizzbuzz-700 active:bg-fizzbuzz-800 focus-visible:ring-fizzbuzz-500",
  secondary:
    "bg-panel-700 text-panel-100 hover:bg-panel-600 active:bg-panel-500 focus-visible:ring-panel-400",
  ghost:
    "bg-transparent text-panel-300 hover:bg-panel-800 hover:text-panel-100 focus-visible:ring-panel-500",
  destructive:
    "bg-red-600 text-white hover:bg-red-700 active:bg-red-800 focus-visible:ring-red-500",
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-base",
};

/**
 * Standard action trigger for the Enterprise FizzBuzz Operations Center.
 * All user-initiated state mutations must be routed through this component
 * to ensure consistent interaction patterns across the platform.
 */
export function Button({
  variant = "primary",
  size = "md",
  className = "",
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center rounded font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-panel-950 disabled:pointer-events-none disabled:opacity-50 ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
