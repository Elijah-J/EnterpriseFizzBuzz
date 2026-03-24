"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Wordmark } from "@/components/brand";
import { Topographic } from "@/components/backgrounds";
import { PageTransition } from "@/components/transitions";
import { CustomCursor } from "@/components/ui/custom-cursor";
import { KeyboardShortcutOverlay } from "@/components/ui/keyboard-shortcut-overlay";
import { useKeyboardNavigation } from "@/lib/hooks/use-keyboard-navigation";
import { Breadcrumbs } from "./breadcrumbs";
import { CommandPalette } from "./command-palette";
import { MobileDrawer } from "./mobile-drawer";
import { Sidebar } from "./sidebar";

interface LayoutShellProps {
  children: React.ReactNode;
}

/**
 * Client-side layout shell managing sidebar, command palette, mobile drawer,
 * and top bar state for the Enterprise FizzBuzz Operations Center.
 *
 * This component encapsulates all interactive layout state — sidebar collapse,
 * command palette visibility, mobile drawer toggling — to keep the root
 * RootLayout as a server component for optimal static export performance.
 */
/**
 * Derives a deterministic numeric seed from a route pathname.
 * Each page in the platform receives a unique topographic terrain
 * background based on its URL path, ensuring visual differentiation
 * without runtime randomness.
 */
function hashPathname(path: string): number {
  let hash = 5381;
  for (let i = 0; i < path.length; i++) {
    hash = ((hash << 5) + hash + path.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

export function LayoutShell({ children }: LayoutShellProps) {
  const router = useRouter();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [shortcutOverlayOpen, setShortcutOverlayOpen] = useState(false);
  const pathname = usePathname();
  const topoSeed = useMemo(() => hashPathname(pathname), [pathname]);

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((prev) => !prev);
  }, []);

  const toggleShortcutOverlay = useCallback(() => {
    setShortcutOverlayOpen((prev) => !prev);
  }, []);

  const navigateTo = useCallback(
    (href: string) => router.push(href),
    [router]
  );

  useKeyboardNavigation({
    onOpenSearch: useCallback(() => setPaletteOpen(true), []),
    onToggleOverlay: toggleShortcutOverlay,
    navigate: navigateTo,
  });

  // Global Cmd+K / Ctrl+K listener
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen((prev) => !prev);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  return (
    <>
      {/* Sidebar — desktop only */}
      <Sidebar collapsed={sidebarCollapsed} onToggle={toggleSidebar} />

      {/* Main content region */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Top bar */}
        <header className="flex h-14 items-center justify-between border-b border-border-subtle bg-surface-base px-4 lg:px-6">
          <div className="flex items-center gap-3">
            {/* Hamburger — mobile only */}
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="lg:hidden flex items-center justify-center w-8 h-8 rounded text-text-muted hover:bg-surface-raised hover:text-text-secondary transition-colors duration-150"
              aria-label="Open navigation menu"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 18 18"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                aria-hidden="true"
              >
                <path d="M3 5h12" />
                <path d="M3 9h12" />
                <path d="M3 13h12" />
              </svg>
            </button>

            {/* Wordmark — visible on mobile when sidebar is hidden */}
            <div className="lg:hidden">
              <Wordmark />
            </div>

            {/* Breadcrumbs — desktop */}
            <div className="hidden lg:block">
              <Breadcrumbs
                items={[
                  { label: "Enterprise FizzBuzz Platform" },
                  { label: "Dashboard" },
                ]}
              />
            </div>
          </div>

          <div className="flex items-center gap-4">
            {/* Search trigger */}
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              className="inline-flex items-center gap-2 rounded bg-transparent text-text-muted hover:bg-surface-raised hover:text-text-secondary px-2.5 py-1.5 text-xs transition-colors duration-150"
              aria-label="Open command palette"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 14 14"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="6" cy="6" r="4.5" />
                <path d="M9.5 9.5 13 13" />
              </svg>
              <kbd className="hidden sm:inline font-mono text-[10px] text-text-muted border border-border-subtle rounded px-1 py-0.5">
                ⌘K
              </kbd>
            </button>

            {/* Operational status indicator */}
            <span className="hidden sm:inline-flex items-center gap-1.5 text-xs text-text-secondary">
              <span className="h-2 w-2 rounded-full bg-accent" />
              All Systems Operational
            </span>
          </div>
        </header>

        {/* Page content */}
        <main className="relative flex-1 overflow-y-auto p-6">
          {/* Generative topographic background — route-seeded terrain */}
          <div className="generative-bg">
            <Topographic seed={topoSeed} density={12} opacity={0.04} />
          </div>
          <PageTransition>{children}</PageTransition>
        </main>
      </div>

      {/* Overlays */}
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onToggleSidebar={toggleSidebar}
      />
      <MobileDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
      <KeyboardShortcutOverlay
        open={shortcutOverlayOpen}
        onClose={() => setShortcutOverlayOpen(false)}
      />

      {/* Custom cursor — warm amber tracking dot with interactive morphing */}
      <CustomCursor />
    </>
  );
}
