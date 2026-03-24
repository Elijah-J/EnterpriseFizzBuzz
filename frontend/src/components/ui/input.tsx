import { forwardRef, type InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {}

/**
 * Standard text input for the Enterprise FizzBuzz Operations Center.
 *
 * Styled with the raised surface background and subtle border tokens. On focus,
 * a 2px amber ring appears at reduced opacity (0.5) to signal active state
 * without visual aggression. The 150ms border-color transition ensures smooth
 * state changes that meet the platform's motion restraint guidelines.
 */
const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className = "", ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={`w-full rounded bg-surface-raised border border-border-subtle px-3 py-2 text-sm text-text-primary placeholder:text-text-muted
          transition-[border-color] duration-150
          focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/50 focus:border-border-default
          disabled:opacity-50 disabled:cursor-not-allowed
          ${className}`}
        {...props}
      />
    );
  },
);

Input.displayName = "Input";

export type { InputProps };
export { Input };
