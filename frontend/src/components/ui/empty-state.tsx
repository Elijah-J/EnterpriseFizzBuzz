import type { ReactNode } from "react";

interface EmptyStateProps {
  /** Primary heading displayed beneath the illustration. */
  title: string;
  /** Supporting description text. */
  description: string;
  /** Optional call-to-action element rendered below the description. */
  action?: ReactNode;
}

/**
 * Empty state placeholder for views with no data to display.
 *
 * Features a geometric SVG illustration using brand token colors (amber accent
 * and warm stone grays) to maintain visual identity even in null states. The
 * Instrument Serif heading and Geist Sans body text follow the platform's
 * typographic hierarchy.
 *
 * The geometric illustration is composed of three overlapping shapes — a circle,
 * a rotated square, and a triangle — representing the convergence of evaluation
 * dimensions in the FizzBuzz pipeline.
 */
export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      {/* Geometric illustration — brand token colors */}
      <svg
        width="120"
        height="120"
        viewBox="0 0 120 120"
        fill="none"
        className="mb-6"
        aria-hidden="true"
      >
        {/* Background circle — muted stone */}
        <circle
          cx="60"
          cy="60"
          r="40"
          fill="var(--surface-overlay)"
          opacity="0.5"
        />
        {/* Rotated square — subtle raised surface */}
        <rect
          x="38"
          y="38"
          width="44"
          height="44"
          rx="4"
          fill="var(--surface-raised)"
          stroke="var(--border-default)"
          strokeWidth="1"
          transform="rotate(12 60 60)"
        />
        {/* Amber accent triangle — brand signal */}
        <polygon
          points="60,30 80,72 40,72"
          fill="var(--accent)"
          opacity="0.2"
          stroke="var(--accent)"
          strokeWidth="1"
          strokeOpacity="0.4"
        />
        {/* Center dot — amber */}
        <circle cx="60" cy="58" r="4" fill="var(--accent)" />
      </svg>

      <h3 className="heading-page mb-2">{title}</h3>
      <p className="text-sm text-text-secondary max-w-md mb-6">{description}</p>
      {action && <div>{action}</div>}
    </div>
  );
}
