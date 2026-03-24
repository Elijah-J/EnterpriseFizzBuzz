/**
 * Enterprise FizzBuzz Platform — Brand Lettermark
 *
 * Geometric F+B composition using three interlocking shapes in the
 * Warm Precision palette. The mark uses overlapping rectangular forms
 * to construct both letters from a unified geometric system. Each shape
 * references a CSS custom property for fill, enabling runtime theme
 * adaptation across all surface contexts.
 *
 * Exports:
 *  - Logo:     Mark only, suitable for compact contexts (sidebar, favicon)
 *  - Wordmark: Mark + "Enterprise FizzBuzz" typeset in serif display
 */

interface LogoProps {
  /** Width of the mark in pixels. Height is derived from the 1:1 aspect ratio. */
  size?: number;
  /** Optional CSS class name for the root SVG element. */
  className?: string;
}

/**
 * The F+B lettermark rendered as an inline SVG. Three geometric shapes —
 * two warm stone verticals and an amber horizontal crossbar — interlock
 * to form an abstract ligature of the letters F and B.
 */
export function Logo({ size = 32, className }: LogoProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="Enterprise FizzBuzz Platform"
      role="img"
    >
      {/* F vertical stem — primary structural element */}
      <rect
        x="8"
        y="6"
        width="8"
        height="36"
        rx="2"
        fill="var(--surface-overlay, #44403C)"
      />
      {/* B vertical stem — secondary structural element */}
      <rect
        x="32"
        y="6"
        width="8"
        height="36"
        rx="2"
        fill="var(--surface-overlay, #44403C)"
      />
      {/* Amber crossbar — connective element linking F to B */}
      <rect
        x="8"
        y="18"
        width="32"
        height="8"
        rx="2"
        fill="var(--accent, #F59E0B)"
      />
      {/* F top bar — completes the F letterform */}
      <rect
        x="8"
        y="6"
        width="22"
        height="8"
        rx="2"
        fill="var(--text-secondary, #A8A29E)"
      />
      {/* B upper bowl — suggests the B's upper counter */}
      <rect
        x="26"
        y="6"
        width="14"
        height="8"
        rx="2"
        fill="var(--text-secondary, #A8A29E)"
      />
      {/* B lower bowl — suggests the B's lower counter */}
      <rect
        x="26"
        y="34"
        width="14"
        height="8"
        rx="2"
        fill="var(--text-secondary, #A8A29E)"
      />
    </svg>
  );
}

interface WordmarkProps {
  /** Height of the logo mark within the wordmark. */
  logoSize?: number;
  /** Optional CSS class name for the root container. */
  className?: string;
}

/**
 * Full brand wordmark: the F+B lettermark followed by "Enterprise FizzBuzz"
 * set in the serif display typeface. Designed for primary brand placement
 * in the sidebar header and marketing contexts.
 */
export function Wordmark({ logoSize = 28, className }: WordmarkProps) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className ?? ""}`}>
      <Logo size={logoSize} />
      <span
        className="text-sm font-normal tracking-tight"
        style={{
          fontFamily: "var(--font-serif, var(--font-geist-sans)), serif",
        }}
      >
        <span className="text-[var(--text-primary,#FAFAF9)]">Enterprise</span>{" "}
        <span className="text-[var(--accent,#F59E0B)]">FizzBuzz</span>
      </span>
    </span>
  );
}
