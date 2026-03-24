import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Dialog } from "../dialog";

describe("Dialog", () => {
  it("does not render when open is false", () => {
    render(
      <Dialog open={false} onClose={() => {}}>
        Hidden content
      </Dialog>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders dialog panel when open is true", () => {
    render(
      <Dialog open={true} onClose={() => {}}>
        Visible content
      </Dialog>,
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("renders children content", () => {
    render(
      <Dialog open={true} onClose={() => {}}>
        Dialog body text
      </Dialog>,
    );
    expect(screen.getByText("Dialog body text")).toBeInTheDocument();
  });

  it("renders title in header when provided", () => {
    render(
      <Dialog open={true} onClose={() => {}} title="System Configuration">
        Content
      </Dialog>,
    );
    expect(screen.getByText("System Configuration")).toBeInTheDocument();
  });

  it("sets aria-label on dialog from title prop", () => {
    render(
      <Dialog open={true} onClose={() => {}} title="Edit Parameters">
        Content
      </Dialog>,
    );
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-label", "Edit Parameters");
  });

  it("sets aria-modal to true", () => {
    render(
      <Dialog open={true} onClose={() => {}}>
        Content
      </Dialog>,
    );
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
  });

  it("fires onClose when Escape key is pressed", () => {
    const handleClose = vi.fn();
    render(
      <Dialog open={true} onClose={handleClose}>
        Content
      </Dialog>,
    );
    fireEvent.keyDown(screen.getByRole("presentation"), { key: "Escape" });
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it("fires onClose when backdrop is clicked", () => {
    const handleClose = vi.fn();
    render(
      <Dialog open={true} onClose={handleClose}>
        Content
      </Dialog>,
    );
    const backdrop = screen.getByRole("presentation").querySelector("[aria-hidden='true']")!;
    fireEvent.click(backdrop);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it("does not fire onClose when dialog panel is clicked", () => {
    const handleClose = vi.fn();
    render(
      <Dialog open={true} onClose={handleClose}>
        <button>Inside</button>
      </Dialog>,
    );
    fireEvent.click(screen.getByText("Inside"));
    expect(handleClose).not.toHaveBeenCalled();
  });

  it("renders close button when title is provided", () => {
    render(
      <Dialog open={true} onClose={() => {}} title="Settings">
        Content
      </Dialog>,
    );
    expect(screen.getByLabelText("Close dialog")).toBeInTheDocument();
  });

  it("fires onClose when close button is clicked", () => {
    const handleClose = vi.fn();
    render(
      <Dialog open={true} onClose={handleClose} title="Settings">
        Content
      </Dialog>,
    );
    fireEvent.click(screen.getByLabelText("Close dialog"));
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it("applies sm size variant class", () => {
    render(
      <Dialog open={true} onClose={() => {}} size="sm">
        Content
      </Dialog>,
    );
    expect(screen.getByRole("dialog")).toHaveClass("max-w-[400px]");
  });

  it("applies md size variant class by default", () => {
    render(
      <Dialog open={true} onClose={() => {}}>
        Content
      </Dialog>,
    );
    expect(screen.getByRole("dialog")).toHaveClass("max-w-[560px]");
  });

  it("applies lg size variant class", () => {
    render(
      <Dialog open={true} onClose={() => {}} size="lg">
        Content
      </Dialog>,
    );
    expect(screen.getByRole("dialog")).toHaveClass("max-w-[720px]");
  });
});
