"use client";

import { Dialog } from "@/components/ui/dialog";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AboutPanelProps {
  /** Controls visibility. */
  open: boolean;
  /** Called when the user dismisses the panel. */
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PLATFORM_STATS = [
  { label: "Lines of Code", value: "300,000+" },
  { label: "Infrastructure Modules", value: "110+" },
  { label: "Custom Exceptions", value: "608" },
  { label: "CLI Flags", value: "315+" },
  { label: "Test Count", value: "~11,400" },
  { label: "Python Files", value: "289" },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Platform information dialog displaying key engineering metrics for the
 * Enterprise FizzBuzz Platform. Accessed via the logo easter egg (5 clicks),
 * this panel provides a comprehensive statistical overview of the codebase
 * scope and complexity.
 *
 * Values are rendered with tabular-nums font variant for consistent column
 * alignment. The footer credits the platform to its chief architect.
 */
export function AboutPanel({ open, onClose }: AboutPanelProps) {
  return (
    <Dialog open={open} onClose={onClose} title="About Enterprise FizzBuzz" size="sm">
      <div className="space-y-4">
        <p className="text-xs text-text-secondary leading-relaxed">
          The Enterprise FizzBuzz Platform is a mission-critical evaluation
          infrastructure delivering production-grade divisibility analysis at
          scale. Every subsystem is technically faithful to its real-world
          counterpart.
        </p>

        <div className="grid grid-cols-2 gap-3">
          {PLATFORM_STATS.map((stat) => (
            <div key={stat.label} className="rounded-lg border border-border-subtle bg-surface-base p-3">
              <p className="text-[10px] text-text-muted uppercase tracking-wider">
                {stat.label}
              </p>
              <p className="text-lg font-mono font-semibold text-text-primary mt-1 tabular-nums">
                {stat.value}
              </p>
            </div>
          ))}
        </div>

        <div className="border-t border-border-subtle pt-3 text-center">
          <p className="text-[10px] text-text-muted">
            Engineered by Bob McFizzington
          </p>
          <p className="text-[10px] text-text-muted mt-0.5">
            Chief FizzBuzz Architect &amp; Distinguished Modular Arithmetic Fellow
          </p>
        </div>
      </div>
    </Dialog>
  );
}
