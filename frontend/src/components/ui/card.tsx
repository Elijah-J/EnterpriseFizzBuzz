import type { HTMLAttributes } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {}

/**
 * Primary container for operational data panels. Each Card represents
 * a discrete monitoring surface within the FizzBuzz Operations Center.
 * Cards maintain visual consistency across all dashboard views and
 * support compositional assembly via CardHeader, CardContent, and CardFooter.
 */
export function Card({ className = "", children, ...props }: CardProps) {
  return (
    <div
      className={`rounded-lg border border-panel-700 bg-panel-800 shadow-sm transition-colors hover:border-panel-600 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({ className = "", children, ...props }: CardProps) {
  return (
    <div className={`border-b border-panel-700 px-4 py-3 ${className}`} {...props}>
      {children}
    </div>
  );
}

export function CardContent({ className = "", children, ...props }: CardProps) {
  return (
    <div className={`px-4 py-3 ${className}`} {...props}>
      {children}
    </div>
  );
}

export function CardFooter({ className = "", children, ...props }: CardProps) {
  return (
    <div
      className={`border-t border-panel-700 px-4 py-3 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
