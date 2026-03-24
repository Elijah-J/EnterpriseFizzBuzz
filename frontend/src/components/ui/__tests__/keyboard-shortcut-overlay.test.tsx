import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { KeyboardShortcutOverlay } from "../keyboard-shortcut-overlay";

describe("KeyboardShortcutOverlay", () => {
  it("does not render when open is false", () => {
    render(<KeyboardShortcutOverlay open={false} onClose={() => {}} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders dialog when open is true", () => {
    render(<KeyboardShortcutOverlay open={true} onClose={() => {}} />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("displays keyboard shortcuts heading", () => {
    render(<KeyboardShortcutOverlay open={true} onClose={() => {}} />);
    expect(screen.getByText("Keyboard Shortcuts")).toBeInTheDocument();
  });

  it("renders shortcut groups by category", () => {
    render(<KeyboardShortcutOverlay open={true} onClose={() => {}} />);
    expect(screen.getByText("Navigation")).toBeInTheDocument();
    expect(screen.getByText("Search & Commands")).toBeInTheDocument();
    expect(screen.getByText("Actions")).toBeInTheDocument();
  });

  it("renders shortcut key descriptions", () => {
    render(<KeyboardShortcutOverlay open={true} onClose={() => {}} />);
    expect(screen.getByText("Next / previous card")).toBeInTheDocument();
    expect(screen.getByText("Open command palette")).toBeInTheDocument();
    expect(screen.getByText("Toggle sidebar")).toBeInTheDocument();
  });

  it("renders shortcut keys in kbd elements", () => {
    render(<KeyboardShortcutOverlay open={true} onClose={() => {}} />);
    const kbdElements = screen.getAllByText("j / k").filter((el) => el.tagName === "KBD");
    expect(kbdElements).toHaveLength(1);
  });

  it("fires onClose when Escape key is pressed", () => {
    const handleClose = vi.fn();
    render(<KeyboardShortcutOverlay open={true} onClose={handleClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it("fires onClose when close button is clicked", () => {
    const handleClose = vi.fn();
    render(<KeyboardShortcutOverlay open={true} onClose={handleClose} />);
    fireEvent.click(screen.getByLabelText("Close keyboard shortcuts"));
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it("sets aria-modal and aria-label on dialog", () => {
    render(<KeyboardShortcutOverlay open={true} onClose={() => {}} />);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-label", "Keyboard shortcuts");
  });

  it("renders hint about disabled shortcuts in input fields", () => {
    render(<KeyboardShortcutOverlay open={true} onClose={() => {}} />);
    expect(screen.getByText(/disabled when typing in input/)).toBeInTheDocument();
  });
});
