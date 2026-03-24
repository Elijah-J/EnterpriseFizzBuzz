import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { CustomCursor } from "../custom-cursor";

// Mock useCursor hook to control cursor state deterministically
vi.mock("@/lib/hooks/use-cursor", () => ({
  useCursor: vi.fn(() => ({
    x: 100,
    y: 200,
    cursorState: "default",
    visible: true,
    isHovering: false,
  })),
}));

import { useCursor } from "@/lib/hooks/use-cursor";
const mockUseCursor = vi.mocked(useCursor);

describe("CustomCursor", () => {
  it("renders cursor container when visible", () => {
    const { container } = render(<CustomCursor />);
    expect(container.querySelector(".custom-cursor-container")).toBeInTheDocument();
  });

  it("returns null when not visible", () => {
    mockUseCursor.mockReturnValue({ x: 0, y: 0, cursorState: "default", visible: false, isHovering: false });
    const { container } = render(<CustomCursor />);
    expect(container.firstChild).toBeNull();
  });

  it("renders with fixed positioning and pointer-events-none", () => {
    mockUseCursor.mockReturnValue({ x: 50, y: 50, cursorState: "default", visible: true, isHovering: false });
    const { container } = render(<CustomCursor />);
    const wrapper = container.querySelector(".custom-cursor-container")!;
    expect(wrapper).toHaveStyle({ pointerEvents: "none", position: "fixed" });
  });

  it("sets aria-hidden on cursor container", () => {
    mockUseCursor.mockReturnValue({ x: 50, y: 50, cursorState: "default", visible: true, isHovering: false });
    const { container } = render(<CustomCursor />);
    expect(container.querySelector("[aria-hidden='true']")).toBeInTheDocument();
  });

  it("renders default cursor as 8px dot", () => {
    mockUseCursor.mockReturnValue({ x: 50, y: 50, cursorState: "default", visible: true, isHovering: false });
    const { container } = render(<CustomCursor />);
    const inner = container.querySelector(".custom-cursor-container > div")!;
    expect(inner).toHaveStyle({ width: "8px", height: "8px" });
  });

  it("renders pointer cursor as 32px ring", () => {
    mockUseCursor.mockReturnValue({ x: 50, y: 50, cursorState: "pointer", visible: true, isHovering: true });
    const { container } = render(<CustomCursor />);
    const inner = container.querySelector(".custom-cursor-container > div")!;
    expect(inner).toHaveStyle({ width: "32px", height: "32px" });
  });

  it("renders text cursor as 2px vertical bar", () => {
    mockUseCursor.mockReturnValue({ x: 50, y: 50, cursorState: "text", visible: true, isHovering: false });
    const { container } = render(<CustomCursor />);
    const inner = container.querySelector(".custom-cursor-container > div")!;
    expect(inner).toHaveStyle({ width: "2px", height: "24px" });
  });
});
