import Link from "next/link";

interface BreadcrumbItem {
  /** Display label for the breadcrumb segment. */
  label: string;
  /** Navigation href. Omit for the current (terminal) segment. */
  href?: string;
}

interface BreadcrumbsProps {
  /** Ordered breadcrumb segments from root to current page. */
  items: BreadcrumbItem[];
}

/**
 * Breadcrumb navigation for the Enterprise FizzBuzz Operations Center.
 *
 * Renders an ordered trail of location segments using Geist Sans. Intermediate
 * segments appear in secondary text color with forward-slash separators in
 * muted tone. The terminal segment uses primary text color and medium weight
 * to indicate the current location.
 *
 * No animation is applied — breadcrumbs serve as a static spatial reference
 * that should remain calm and immediately legible at all times.
 */
export function Breadcrumbs({ items }: BreadcrumbsProps) {
  return (
    <nav className="flex items-center gap-2 text-sm" aria-label="Breadcrumb">
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        return (
          <span key={item.label} className="flex items-center gap-2">
            {index > 0 && <span className="text-text-muted">/</span>}
            {isLast ? (
              <span className="text-text-primary font-medium">
                {item.label}
              </span>
            ) : item.href ? (
              <Link
                href={item.href}
                className="text-text-secondary hover:text-text-primary transition-colors duration-150"
              >
                {item.label}
              </Link>
            ) : (
              <span className="text-text-secondary">{item.label}</span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
