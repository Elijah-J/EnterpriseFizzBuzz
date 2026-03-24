import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CommandPalette } from "../command-palette";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

describe("CommandPalette", () => {
  beforeEach(() => {
    mockPush.mockClear();
    localStorage.clear();
  });

  it("renders nothing when closed", () => {
    const { container } = render(
      <CommandPalette open={false} onClose={vi.fn()} />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("renders a dialog when open", () => {
    render(<CommandPalette open={true} onClose={vi.fn()} />);
    expect(
      screen.getByRole("dialog", { name: "Command palette" }),
    ).toBeInTheDocument();
  });

  it("renders the search input with placeholder", () => {
    render(<CommandPalette open={true} onClose={vi.fn()} />);
    expect(
      screen.getByPlaceholderText("Search pages and actions..."),
    ).toBeInTheDocument();
  });

  it("renders Navigation section with all 21 navigation items", () => {
    render(<CommandPalette open={true} onClose={vi.fn()} />);
    expect(screen.getByText("Navigation")).toBeInTheDocument();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Archaeological Recovery")).toBeInTheDocument();
  });

  it("renders Actions section", () => {
    render(<CommandPalette open={true} onClose={vi.fn()} />);
    expect(screen.getByText("Actions")).toBeInTheDocument();
    expect(screen.getByText("Toggle Sidebar")).toBeInTheDocument();
    expect(screen.getByText("Keyboard Shortcuts")).toBeInTheDocument();
    expect(screen.getByText("Refresh Data")).toBeInTheDocument();
  });

  it("filters items based on search query", () => {
    render(<CommandPalette open={true} onClose={vi.fn()} />);
    const input = screen.getByPlaceholderText("Search pages and actions...");
    fireEvent.change(input, { target: { value: "Quantum" } });
    expect(screen.getByText("Quantum Workbench")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
  });

  it("shows no results message when query matches nothing", () => {
    render(<CommandPalette open={true} onClose={vi.fn()} />);
    const input = screen.getByPlaceholderText("Search pages and actions...");
    fireEvent.change(input, { target: { value: "xyznonexistent" } });
    expect(screen.getByText("No results found.")).toBeInTheDocument();
  });

  it("calls onClose when Escape is pressed", () => {
    const onClose = vi.fn();
    render(<CommandPalette open={true} onClose={onClose} />);
    const dialog = screen.getByRole("dialog");
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose when backdrop is clicked", () => {
    const onClose = vi.fn();
    const { container } = render(
      <CommandPalette open={true} onClose={onClose} />,
    );
    // Backdrop is the first child div with bg-surface-ground
    const backdrop = container.querySelector(".bg-surface-ground\\/80");
    fireEvent.click(backdrop!);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("navigates and closes when a navigation item is selected via Enter", () => {
    const onClose = vi.fn();
    render(<CommandPalette open={true} onClose={onClose} />);
    const dialog = screen.getByRole("dialog");
    // First item is Dashboard, press Enter to select it
    fireEvent.keyDown(dialog, { key: "Enter" });
    expect(mockPush).toHaveBeenCalledWith("/");
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("navigates with ArrowDown and selects with Enter", () => {
    const onClose = vi.fn();
    render(<CommandPalette open={true} onClose={onClose} />);
    const dialog = screen.getByRole("dialog");
    // Move down to second item (Evaluation Console)
    fireEvent.keyDown(dialog, { key: "ArrowDown" });
    fireEvent.keyDown(dialog, { key: "Enter" });
    expect(mockPush).toHaveBeenCalledWith("/evaluate");
  });

  it("displays keyboard shortcut hints for action items", () => {
    render(<CommandPalette open={true} onClose={vi.fn()} />);
    // Toggle Sidebar has shortcut ⌘B
    const kbdElements = document.querySelectorAll("kbd");
    const shortcuts = Array.from(kbdElements).map((el) => el.textContent);
    expect(shortcuts).toContain("⌘B");
    expect(shortcuts).toContain("?");
  });

  it("calls onToggleSidebar when Toggle Sidebar action is selected", () => {
    const onToggleSidebar = vi.fn();
    const onClose = vi.fn();
    render(
      <CommandPalette
        open={true}
        onClose={onClose}
        onToggleSidebar={onToggleSidebar}
      />,
    );
    fireEvent.click(screen.getByText("Toggle Sidebar"));
    expect(onToggleSidebar).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("records recent commands to localStorage", () => {
    const onClose = vi.fn();
    render(<CommandPalette open={true} onClose={onClose} />);
    fireEvent.click(screen.getByText("Dashboard"));
    const stored = JSON.parse(
      localStorage.getItem("efp-recent-commands") ?? "[]",
    );
    expect(stored).toContain("Dashboard");
  });

  it("sets aria-modal on the dialog", () => {
    render(<CommandPalette open={true} onClose={vi.fn()} />);
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
  });
});
