import type { HTMLAttributes } from "react";

interface SeparatorProps extends HTMLAttributes<HTMLHRElement> {}

/**
 * Visual separator for structural delineation within operational panels.
 *
 * Renders a horizontal rule using the subtle border token, providing
 * low-contrast division between content sections. The minimal visual
 * weight ensures structural clarity without competing for attention
 * in data-dense layouts.
 */
export function Separator({ className = "", ...props }: SeparatorProps) {
  return (
    <hr className={`border-t border-border-subtle ${className}`} {...props} />
  );
}
