"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
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

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}

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

interface MobileDrawerProps {
  /** Whether the drawer is visible. */
  open: boolean;
  /** Callback to close the drawer. */
  onClose: () => void;
}

/**
 * Mobile navigation drawer for the Enterprise FizzBuzz Operations Center.
 *
 * Slides in from the left edge with a CSS transform animation (200ms).
 * A dark overlay backdrop provides visual separation from the main content
 * without blur effects. Closes on overlay click, Escape key, or navigation
 * selection.
 *
 * Contains the same navigation hierarchy as the desktop Sidebar to ensure
 * feature parity across viewport sizes.
 */
export function MobileDrawer({ open, onClose }: MobileDrawerProps) {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Close on navigation — pathname change indicates route transition
  const pathnameRef = useRef(pathname);
  useEffect(() => {
    if (pathnameRef.current !== pathname) {
      pathnameRef.current = pathname;
      if (open) onClose();
    }
  }, [pathname, open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      {/* Overlay backdrop — solid dark */}
      {/* biome-ignore lint/a11y/useKeyWithClickEvents: Backdrop dismiss on click is standard drawer UX */}
      {/* biome-ignore lint/a11y/noStaticElementInteractions: Backdrop overlay uses click for standard dismiss pattern */}
      <div
        className="absolute inset-0 bg-surface-ground/60"
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div
        className="absolute left-0 top-0 bottom-0 w-72 bg-surface-base border-r border-border-subtle overflow-y-auto"
        style={{
          animation: "slideInFromLeft 200ms ease-out",
        }}
      >
        <div className="px-4 py-4">
          {navSections.map((section) => (
            <div key={section.label} className="mb-4">
              <p className="heading-section px-2 mb-1">{section.label}</p>
              <ul className="space-y-0.5">
                {section.items.map((item) => {
                  const active = isActive(item.href);
                  const Icon = item.icon;
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        className={`flex items-center gap-3 rounded px-2 py-1.5 text-sm transition-colors duration-150 ${
                          active
                            ? "bg-surface-raised text-text-primary border-l-2 border-l-[var(--accent)] -ml-0.5 pl-[calc(0.5rem+2px)]"
                            : "text-text-secondary hover:bg-surface-raised"
                        }`}
                      >
                        <Icon className="shrink-0" />
                        <span>{item.label}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
