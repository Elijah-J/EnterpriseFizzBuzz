import type { HTMLAttributes, ReactNode } from "react";

interface FocusRingProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

/**
 * Keyboard focus indicator wrapper for the Enterprise FizzBuzz Platform.
 *
 * Renders a warm amber outline ring (2px, rounded) around the wrapped element
 * when it receives keyboard focus via the `:focus-visible` CSS pseudo-class.
 * The ring is invisible during mouse interactions, ensuring visual clarity
 * for pointer-driven operators while maintaining full keyboard accessibility.
 *
 * This component standardizes the focus treatment across all interactive
 * elements in the Operations Center, replacing browser-default focus outlines
 * with the Warm Precision amber accent.
 */
export function FocusRing({ children, className = "", ...props }: FocusRingProps) {
  return (
    <div
      className={`rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-surface-ground ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
