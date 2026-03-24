"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Tooltip } from "@/components/ui/tooltip";
import {
  AlertsIcon,
  AnalyticsIcon,
  ArchaeologyIcon,
  AuditIcon,
  BlockchainIcon,
  CacheIcon,
  ChaosIcon,
  ComplianceIcon,
  ConfigurationIcon,
  ConsensusIcon,
  DashboardIcon,
  DigitalTwinIcon,
  EvaluateIcon,
  EvolutionIcon,
  FederatedLearningIcon,
  FinOpsIcon,
  MetricsIcon,
  MonitorIcon,
  QuantumIcon,
  TracesIcon,
} from "./sidebar-icons";

/**
 * Navigation item descriptor for the sidebar menu system.
 */
interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}

/**
 * Grouped navigation section within the sidebar hierarchy.
 */
interface NavSection {
  label: string;
  items: NavItem[];
}

const navSections: NavSection[] = [
  {
    label: "Operations",
    items: [
      { label: "Dashboard", href: "/", icon: DashboardIcon },
      { label: "Evaluation Console", href: "/evaluate", icon: EvaluateIcon },
      {
        label: "Infrastructure Monitor",
        href: "/monitor/health",
        icon: MonitorIcon,
      },
    ],
  },
  {
    label: "Monitor",
    items: [
      { label: "Metrics", href: "/monitor/metrics", icon: MetricsIcon },
      { label: "Traces", href: "/monitor/traces", icon: TracesIcon },
      { label: "Alerts", href: "/monitor/alerts", icon: AlertsIcon },
      { label: "Cache Coherence", href: "/cache", icon: CacheIcon },
      { label: "Consensus", href: "/monitor/consensus", icon: ConsensusIcon },
      { label: "SLA Budget", href: "/monitor/sla", icon: MonitorIcon },
    ],
  },
  {
    label: "Platform",
    items: [
      { label: "Compliance", href: "/compliance", icon: ComplianceIcon },
      { label: "Blockchain", href: "/blockchain", icon: BlockchainIcon },
      { label: "Analytics", href: "/analytics", icon: AnalyticsIcon },
      {
        label: "Configuration",
        href: "/configuration",
        icon: ConfigurationIcon,
      },
      { label: "Audit Log", href: "/audit", icon: AuditIcon },
      { label: "Chaos Engineering", href: "/chaos", icon: ChaosIcon },
      { label: "Digital Twin", href: "/digital-twin", icon: DigitalTwinIcon },
    ],
  },
  {
    label: "Finance",
    items: [{ label: "FinOps", href: "/finops", icon: FinOpsIcon }],
  },
  {
    label: "Research",
    items: [
      { label: "Quantum Workbench", href: "/quantum", icon: QuantumIcon },
      {
        label: "Evolution Observatory",
        href: "/evolution",
        icon: EvolutionIcon,
      },
      {
        label: "Federated Learning",
        href: "/federated-learning",
        icon: FederatedLearningIcon,
      },
      {
        label: "Archaeological Recovery",
        href: "/archaeology",
        icon: ArchaeologyIcon,
      },
    ],
  },
];

/**
 * Chevron icon used for the sidebar collapse toggle.
 */
function ChevronIcon({ collapsed }: { collapsed: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={`transition-transform duration-200 ${collapsed ? "rotate-180" : ""}`}
    >
      <path d="M10 4l-4 4 4 4" />
    </svg>
  );
}

interface SidebarProps {
  /** Controlled collapse state. */
  collapsed: boolean;
  /** Callback to toggle collapse state. */
  onToggle: () => void;
}

/**
 * Primary navigation sidebar for the Enterprise FizzBuzz Operations Center.
 *
 * Supports two display modes: expanded (w-60) showing icon + label, and
 * collapsed (w-14) showing icon-only with tooltip labels on hover. The
 * transition between states uses a 200ms duration for spatial awareness
 * without delay.
 *
 * Active navigation state is indicated by a raised surface background,
 * primary text color, and a 2px amber left-edge accent bar. This triple
 * signal ensures state is communicated through color, luminance, and
 * spatial position simultaneously.
 *
 * Hidden below the lg breakpoint — mobile navigation is handled by the
 * MobileDrawer component.
 */
export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  return (
    <aside
      className={`hidden lg:flex lg:flex-col border-r border-border-subtle bg-surface-base transition-all duration-200 ${
        collapsed ? "lg:w-14" : "lg:w-60"
      }`}
    >
      {/* Collapse toggle */}
      <div className="flex h-14 items-center border-b border-border-subtle px-3">
        <button
          type="button"
          onClick={onToggle}
          className="flex items-center justify-center w-8 h-8 rounded text-text-muted hover:bg-surface-raised hover:text-text-secondary transition-colors duration-150"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <ChevronIcon collapsed={collapsed} />
        </button>
      </div>

      {/* Navigation sections */}
      <nav className="flex-1 overflow-y-auto py-2 px-2" aria-label="Main">
        {navSections.map((section) => (
          <div key={section.label} className="mb-3">
            {!collapsed && (
              <p className="heading-section px-2 mb-1">{section.label}</p>
            )}
            <ul className="relative space-y-0.5">
              {section.items.map((item) => {
                const active = isActive(item.href);
                const Icon = item.icon;
                const linkContent = (
                  <Link
                    href={item.href}
                    className={`relative flex items-center gap-3 rounded px-2 py-1.5 text-sm transition-all duration-200 ${
                      active
                        ? "bg-surface-raised text-text-primary"
                        : "text-text-secondary hover:bg-surface-raised"
                    } ${collapsed ? "justify-center" : ""}`}
                  >
                    {/* Active indicator bar — slides into position via CSS transition */}
                    <span
                      className="absolute left-0 top-1 bottom-1 w-[2px] rounded-full transition-all duration-200"
                      style={{
                        backgroundColor: active ? "var(--accent)" : "transparent",
                        transform: active ? "scaleY(1)" : "scaleY(0)",
                      }}
                    />
                    <Icon className="shrink-0" />
                    {!collapsed && (
                      <span className="truncate">{item.label}</span>
                    )}
                  </Link>
                );

                return (
                  <li key={item.href}>
                    {collapsed ? (
                      <Tooltip content={item.label} side="right">
                        {linkContent}
                      </Tooltip>
                    ) : (
                      linkContent
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Bottom section */}
      <div className="border-t border-border-subtle px-3 py-3">
        {collapsed ? (
          <p className="text-[10px] text-text-muted text-center">0.1</p>
        ) : (
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-muted">v0.1.0</span>
            <kbd className="text-[10px] text-text-muted font-mono border border-border-subtle rounded px-1 py-0.5">
              ⌘K
            </kbd>
          </div>
        )}
      </div>
    </aside>
  );
}
