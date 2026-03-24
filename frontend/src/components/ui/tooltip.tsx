"use client";

import { type ReactNode, useId, useState } from "react";

type TooltipSide = "top" | "bottom" | "left" | "right";

interface TooltipProps {
  /** Text content displayed within the tooltip surface. */
  content: string;
  /** Preferred placement relative to the trigger element. Default "top". */
  side?: TooltipSide;
  /** Trigger element that activates the tooltip on hover/focus. */
  children: ReactNode;
}

const positionStyles: Record<TooltipSide, string> = {
  top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
  bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
  left: "right-full top-1/2 -translate-y-1/2 mr-2",
  right: "left-full top-1/2 -translate-y-1/2 ml-2",
};

/**
 * Contextual information overlay for the Enterprise FizzBuzz Operations Center.
 *
 * Renders a positioned tooltip surface on hover and keyboard focus. The tooltip
 * uses the overlay surface token with a subtle border to maintain the layered
 * depth system without resorting to shadows or blur effects.
 *
 * The 150ms fade-in transition provides perceptible but non-disruptive feedback
 * that information is available without demanding attention.
 */
export function Tooltip({ content, side = "top", children }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const tooltipId = useId();

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: Tooltip wrapper captures hover/focus events for child elements
    <span
      className="relative inline-flex"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocusCapture={() => setVisible(true)}
      onBlurCapture={() => setVisible(false)}
      aria-describedby={tooltipId}
    >
      {children}
      <span
        id={tooltipId}
        role="tooltip"
        className={`absolute z-50 px-2.5 py-1.5 text-xs rounded border whitespace-nowrap pointer-events-none
          bg-surface-overlay text-text-primary border-border-subtle
          transition-opacity duration-150
          ${positionStyles[side]}
          ${visible ? "opacity-100" : "opacity-0"}`}
      >
        {content}
      </span>
    </span>
  );
}
