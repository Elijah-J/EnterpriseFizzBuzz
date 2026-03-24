"use client";

import { useRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { useMagnetic } from "@/lib/hooks/use-magnetic";
import { Button } from "./button";

interface MagneticButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "destructive";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: ReactNode;
  /** Magnetic displacement strength (0-1). Default: 0.3 */
  magneticStrength?: number;
  /** Magnetic activation radius in pixels. Default: 100 */
  magneticRadius?: number;
}

/**
 * Enhanced action trigger with magnetic cursor-following behavior.
 *
 * Wraps the standard Button component with the useMagnetic hook, causing
 * the button to subtly track the cursor when it enters the activation
 * radius. This micro-interaction communicates interactivity and creates
 * a physical, high-fidelity feel appropriate for primary call-to-action
 * surfaces in the Enterprise FizzBuzz Operations Center.
 *
 * Maximum displacement is capped at 4px with a spring-based return,
 * ensuring the effect remains subtle and does not interfere with
 * Fitts' Law targeting efficiency.
 */
export function MagneticButton({
  magneticStrength = 0.3,
  magneticRadius = 100,
  children,
  ...props
}: MagneticButtonProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  useMagnetic(wrapperRef, {
    strength: magneticStrength,
    radius: magneticRadius,
  });

  return (
    <div ref={wrapperRef} className="inline-block">
      <Button {...props}>{children}</Button>
    </div>
  );
}
