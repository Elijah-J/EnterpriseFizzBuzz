import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { CopyButton } from "../copy-button";

describe("CopyButton", () => {
  const mockWriteText = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.useFakeTimers();
    Object.assign(navigator, {
      clipboard: {
        writeText: mockWriteText,
      },
    });
    mockWriteText.mockClear();
  });

  it("renders a button element", () => {
    render(<CopyButton text="test" />);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("has aria-label for copy action by default", () => {
    render(<CopyButton text="test" />);
    expect(screen.getByRole("button")).toHaveAttribute("aria-label", "Copy to clipboard");
  });

  it("copies text to clipboard on click", async () => {
    render(<CopyButton text="0xDEADBEEF" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(mockWriteText).toHaveBeenCalledWith("0xDEADBEEF");
  });

  it("shows copied confirmation after successful copy", async () => {
    render(<CopyButton text="hash" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(screen.getByRole("button")).toHaveAttribute("aria-label", "Copied to clipboard");
  });

  it("reverts to default state after timeout", async () => {
    render(<CopyButton text="hash" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(screen.getByRole("button")).toHaveAttribute("aria-label", "Copied to clipboard");
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByRole("button")).toHaveAttribute("aria-label", "Copy to clipboard");
  });

  it("renders checkmark SVG after copy", async () => {
    render(<CopyButton text="hash" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    const svg = screen.getByRole("button").querySelector("svg");
    expect(svg).toHaveClass("text-fizz-400");
  });

  it("merges custom className", () => {
    render(<CopyButton text="test" className="ml-2" />);
    expect(screen.getByRole("button")).toHaveClass("ml-2");
  });

});
