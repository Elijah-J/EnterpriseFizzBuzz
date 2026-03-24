import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { LayoutShell } from "../layout-shell";

// Mock next/navigation
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => "/",
}));

// Mock all child components to isolate LayoutShell behavior
vi.mock("@/components/brand", () => ({
  Wordmark: () => <div data-testid="wordmark">Wordmark</div>,
}));

vi.mock("@/components/backgrounds", () => ({
  Topographic: () => <div data-testid="topographic" />,
}));

vi.mock("@/components/delight/confetti", () => ({
  Confetti: vi.fn(
    // biome-ignore lint/suspicious/noExplicitAny: test mock
    (props: any) => <div data-testid="confetti" ref={props.ref} />,
  ),
}));

vi.mock("@/components/transitions", () => ({
  PageTransition: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="page-transition">{children}</div>
  ),
}));

vi.mock("@/components/ui/custom-cursor", () => ({
  CustomCursor: () => <div data-testid="custom-cursor" />,
}));

vi.mock("@/components/ui/keyboard-shortcut-overlay", () => ({
  KeyboardShortcutOverlay: ({
    open,
    onClose,
  }: {
    open: boolean;
    onClose: () => void;
  }) =>
    open ? (
      <div data-testid="shortcut-overlay">
        <button type="button" onClick={onClose}>Close overlay</button>
      </div>
    ) : null,
}));

vi.mock("@/components/ui/live-indicator", () => ({
  LiveIndicator: () => <div data-testid="live-indicator" />,
}));

vi.mock("@/lib/hooks/use-keyboard-navigation", () => ({
  useKeyboardNavigation: vi.fn(),
}));

vi.mock("@/lib/hooks/use-konami", () => ({
  useKonami: () => ({ activated: false }),
}));

vi.mock("../breadcrumbs", () => ({
  Breadcrumbs: ({ items }: { items: { label: string }[] }) => (
    <nav data-testid="breadcrumbs">
      {items.map((i) => (
        <span key={i.label}>{i.label}</span>
      ))}
    </nav>
  ),
}));

vi.mock("../command-palette", () => ({
  CommandPalette: ({
    open,
    onClose,
  }: {
    open: boolean;
    onClose: () => void;
  }) =>
    open ? (
      <div data-testid="command-palette" role="dialog">
        <button type="button" onClick={onClose}>Close palette</button>
      </div>
    ) : null,
}));

vi.mock("../mobile-drawer", () => ({
  MobileDrawer: ({
    open,
    onClose,
  }: {
    open: boolean;
    onClose: () => void;
  }) =>
    open ? (
      <div data-testid="mobile-drawer">
        <button type="button" onClick={onClose}>Close drawer</button>
      </div>
    ) : null,
}));

vi.mock("../sidebar", () => ({
  Sidebar: ({
    collapsed,
    onToggle,
  }: {
    collapsed: boolean;
    onToggle: () => void;
  }) => (
    <aside data-testid="sidebar" data-collapsed={collapsed}>
      <button type="button" onClick={onToggle}>Toggle sidebar</button>
    </aside>
  ),
}));

describe("LayoutShell", () => {
  beforeEach(() => {
    mockPush.mockClear();
  });

  it("renders children inside the content area", () => {
    render(
      <LayoutShell>
        <div data-testid="child-content">Hello</div>
      </LayoutShell>,
    );
    expect(screen.getByTestId("child-content")).toBeInTheDocument();
  });

  it("renders the sidebar component", () => {
    render(<LayoutShell><div /></LayoutShell>);
    expect(screen.getByTestId("sidebar")).toBeInTheDocument();
  });

  it("renders the topographic background", () => {
    render(<LayoutShell><div /></LayoutShell>);
    expect(screen.getByTestId("topographic")).toBeInTheDocument();
  });

  it("renders the wordmark in mobile header area", () => {
    render(<LayoutShell><div /></LayoutShell>);
    expect(screen.getByTestId("wordmark")).toBeInTheDocument();
  });

  it("renders the live indicator", () => {
    render(<LayoutShell><div /></LayoutShell>);
    expect(screen.getByTestId("live-indicator")).toBeInTheDocument();
  });

  it("renders breadcrumbs with platform context", () => {
    render(<LayoutShell><div /></LayoutShell>);
    expect(screen.getByTestId("breadcrumbs")).toBeInTheDocument();
  });

  it("renders the custom cursor", () => {
    render(<LayoutShell><div /></LayoutShell>);
    expect(screen.getByTestId("custom-cursor")).toBeInTheDocument();
  });

  it("renders the confetti overlay container", () => {
    render(<LayoutShell><div /></LayoutShell>);
    expect(screen.getByTestId("confetti")).toBeInTheDocument();
  });

  it("opens mobile drawer when hamburger button is clicked", () => {
    render(<LayoutShell><div /></LayoutShell>);
    const hamburger = screen.getByRole("button", {
      name: "Open navigation menu",
    });
    fireEvent.click(hamburger);
    expect(screen.getByTestId("mobile-drawer")).toBeInTheDocument();
  });

  it("opens command palette when search button is clicked", () => {
    render(<LayoutShell><div /></LayoutShell>);
    const searchBtn = screen.getByRole("button", {
      name: "Open command palette",
    });
    fireEvent.click(searchBtn);
    expect(screen.getByTestId("command-palette")).toBeInTheDocument();
  });

  it("opens command palette on Ctrl+K", () => {
    render(<LayoutShell><div /></LayoutShell>);
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    expect(screen.getByTestId("command-palette")).toBeInTheDocument();
  });

  it("wraps children in PageTransition", () => {
    render(
      <LayoutShell>
        <p>Test</p>
      </LayoutShell>,
    );
    expect(screen.getByTestId("page-transition")).toBeInTheDocument();
  });
});
