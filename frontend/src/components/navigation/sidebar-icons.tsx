/**
 * Sidebar Navigation Icon Library
 *
 * A curated set of 20 stroke-based SVG icons sized at 18x18 pixels with
 * 1.5px stroke width. Each icon uses `currentColor` for stroke, enabling
 * automatic color inheritance from the parent navigation item's state
 * (muted, active, hovered).
 *
 * The geometric style prioritizes clarity at small sizes over ornamental
 * detail, ensuring legibility in both expanded and collapsed sidebar states.
 */

interface IconProps {
  className?: string;
}

/**
 * Base SVG wrapper applying standard icon attributes. Using a component
 * rather than a spread object ensures static analysis tools can verify
 * aria-hidden is present on each SVG element.
 */
function Icon({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <svg
      width={18}
      height={18}
      viewBox="0 0 18 18"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={true}
      className={className}
    >
      {children}
    </svg>
  );
}

export function DashboardIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <rect x="2" y="2" width="6" height="6" rx="1" />
      <rect x="10" y="2" width="6" height="3" rx="1" />
      <rect x="10" y="7" width="6" height="9" rx="1" />
      <rect x="2" y="10" width="6" height="6" rx="1" />
    </Icon>
  );
}

export function EvaluateIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <path d="M9 2v14" />
      <path d="M2 9h14" />
      <circle cx="9" cy="9" r="6" />
    </Icon>
  );
}

export function MonitorIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <rect x="2" y="3" width="14" height="10" rx="1.5" />
      <path d="M6 16h6" />
      <path d="M9 13v3" />
    </Icon>
  );
}

export function MetricsIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <path d="M2 14l4-5 3 3 5-7 2 2" />
      <path d="M2 16h14" />
    </Icon>
  );
}

export function TracesIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <path d="M2 5h4l2 8h4l2-8h2" />
    </Icon>
  );
}

export function AlertsIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <path d="M9 2l7 13H2L9 2z" />
      <path d="M9 7v4" />
      <circle cx="9" cy="13" r="0.5" fill="currentColor" stroke="none" />
    </Icon>
  );
}

export function CacheIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <ellipse cx="9" cy="5" rx="6" ry="2.5" />
      <path d="M3 5v4c0 1.38 2.69 2.5 6 2.5s6-1.12 6-2.5V5" />
      <path d="M3 9v4c0 1.38 2.69 2.5 6 2.5s6-1.12 6-2.5V9" />
    </Icon>
  );
}

export function ConsensusIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <circle cx="9" cy="4" r="2" />
      <circle cx="4" cy="14" r="2" />
      <circle cx="14" cy="14" r="2" />
      <path d="M9 6v3l-4 3" />
      <path d="M9 9l4 3" />
    </Icon>
  );
}

export function ComplianceIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <rect x="3" y="2" width="12" height="14" rx="1.5" />
      <path d="M6 6h6" />
      <path d="M6 9h6" />
      <path d="M6 12h3" />
    </Icon>
  );
}

export function BlockchainIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <rect x="2" y="2" width="5" height="5" rx="0.5" />
      <rect x="11" y="2" width="5" height="5" rx="0.5" />
      <rect x="6.5" y="11" width="5" height="5" rx="0.5" />
      <path d="M7 4.5h4" />
      <path d="M4.5 7v4h2" />
      <path d="M13.5 7v4h-2" />
    </Icon>
  );
}

export function AnalyticsIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <path d="M4 14V8" />
      <path d="M7 14V5" />
      <path d="M10 14V9" />
      <path d="M13 14V3" />
    </Icon>
  );
}

export function ConfigurationIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <circle cx="9" cy="9" r="3" />
      <path d="M9 2v2" />
      <path d="M9 14v2" />
      <path d="M2 9h2" />
      <path d="M14 9h2" />
      <path d="M4.05 4.05l1.41 1.41" />
      <path d="M12.54 12.54l1.41 1.41" />
      <path d="M4.05 13.95l1.41-1.41" />
      <path d="M12.54 5.46l1.41-1.41" />
    </Icon>
  );
}

export function AuditIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <path d="M12 2H4.5A1.5 1.5 0 003 3.5v11A1.5 1.5 0 004.5 16h9a1.5 1.5 0 001.5-1.5V5L12 2z" />
      <path d="M12 2v3h3" />
      <path d="M6 8l2 2 4-4" />
    </Icon>
  );
}

export function ChaosIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <path d="M9 2a7 7 0 110 14A7 7 0 019 2z" />
      <path d="M7 7l4 4" />
      <path d="M11 7l-4 4" />
    </Icon>
  );
}

export function DigitalTwinIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <rect x="2" y="5" width="6" height="8" rx="1" />
      <rect x="10" y="5" width="6" height="8" rx="1" />
      <path d="M8 8h2" />
      <path d="M8 10h2" />
    </Icon>
  );
}

export function FinOpsIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <path d="M9 2v14" />
      <path d="M12 4H7.5a2.5 2.5 0 000 5H10.5a2.5 2.5 0 010 5H6" />
    </Icon>
  );
}

export function QuantumIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <circle cx="9" cy="9" r="2" />
      <ellipse cx="9" cy="9" rx="7" ry="3" />
      <ellipse cx="9" cy="9" rx="7" ry="3" transform="rotate(60 9 9)" />
      <ellipse cx="9" cy="9" rx="7" ry="3" transform="rotate(120 9 9)" />
    </Icon>
  );
}

export function EvolutionIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <path d="M3 14c2-4 4-6 6-10" />
      <path d="M9 4c2 4 4 6 6 10" />
      <path d="M5 10c2 1 4 1 8 0" />
    </Icon>
  );
}

export function FederatedLearningIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <circle cx="9" cy="9" r="2.5" />
      <circle cx="3" cy="3" r="1.5" />
      <circle cx="15" cy="3" r="1.5" />
      <circle cx="3" cy="15" r="1.5" />
      <circle cx="15" cy="15" r="1.5" />
      <path d="M4.2 4.2l3.3 3.3" />
      <path d="M13.8 4.2l-3.3 3.3" />
      <path d="M4.2 13.8l3.3-3.3" />
      <path d="M13.8 13.8l-3.3-3.3" />
    </Icon>
  );
}

export function ArchaeologyIcon({ className }: IconProps) {
  return (
    <Icon className={className}>
      <path d="M4 16l5-5" />
      <circle cx="11" cy="7" r="4" />
      <path d="M13 2l3 3" />
    </Icon>
  );
}
