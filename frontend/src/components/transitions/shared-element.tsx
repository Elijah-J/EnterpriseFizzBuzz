"use client";

import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

interface SharedElementProps extends HTMLAttributes<HTMLDivElement> {
  /**
   * Unique transition identifier for this element. When two SharedElement
   * instances on different pages share the same `transitionName`, the
   * View Transitions API will morph between them during page navigation.
   */
  transitionName: string;
  children: ReactNode;
}

/**
 * Shared element transition marker for cross-page visual continuity.
 *
 * Assigns a `view-transition-name` CSS property to the wrapped element,
 * enabling the View Transitions API to identify corresponding elements
 * across page navigations and generate morphing animations between them.
 *
 * When a DataCard on the Executive Dashboard links to a detail page, the
 * card header marked with SharedElement will smoothly morph into the
 * detail page header, maintaining spatial continuity and reducing
 * cognitive context-switching overhead for the operator.
 *
 * In browsers without View Transitions API support, this component renders
 * as a transparent wrapper with no visual effect — the standard crossfade
 * fallback from PageTransition handles the transition instead.
 */
export function SharedElement({
  transitionName,
  children,
  style,
  ...props
}: SharedElementProps) {
  const mergedStyle: CSSProperties = {
    ...style,
    viewTransitionName: transitionName,
  };

  return (
    <div style={mergedStyle} {...props}>
      {children}
    </div>
  );
}
