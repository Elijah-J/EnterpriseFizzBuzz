/**
 * Tabular numeral display wrapper.
 *
 * Ensures all enclosed numeric content renders with `tabular-nums` font
 * variant and precise letter-spacing, preventing layout shifts when values
 * change in real-time dashboards. Large numbers receive subtle negative
 * tracking to maintain optical density, while decimal-aligned values use
 * monospace digit widths for vertical column consistency.
 *
 * This component is critical for the metrics displays throughout the
 * Operations Center, where fluctuating values must not cause horizontal
 * jitter in adjacent elements.
 */

interface TabularNumberProps {
  /** The numeric content to display. */
  children: React.ReactNode;
  /** Additional CSS classes. */
  className?: string;
  /** When true, applies decimal alignment via text-align-last. */
  alignDecimal?: boolean;
}

export function TabularNumber({
  children,
  className = "",
  alignDecimal = false,
}: TabularNumberProps) {
  return (
    <span
      className={`tabular-nums ${alignDecimal ? "tabular-number-decimal" : ""} ${className}`}
    >
      {children}
    </span>
  );
}
