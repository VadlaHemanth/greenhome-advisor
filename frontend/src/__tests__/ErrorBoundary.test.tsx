import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "../ErrorBoundary";

function BrokenResult(): never {
  throw new Error("private-home-input-and-provider-details");
}

describe("generic render recovery", () => {
  it("passes through successful content", () => {
    render(
      <ErrorBoundary>
        <p>Current engine result</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("Current engine result")).toBeTruthy();
  });
  it("shows recovery without echoing raw exception details", () => {
    // React development mode reports caught errors to its console; production
    // component rendering/logging is checked independently below.
    vi.spyOn(console, "error").mockImplementation(() => {});
    const reload = vi.fn();
    render(
      <ErrorBoundary onReload={reload}>
        <BrokenResult />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert").textContent).toContain(
      "No replacement estimate has been invented",
    );
    expect(document.body.textContent).not.toContain(
      "private-home-input-and-provider-details",
    );
    fireEvent.click(screen.getByRole("button", { name: "Reload workspace" }));
    expect(reload).toHaveBeenCalledOnce();
  });
  it("does not add error logging or telemetry from the boundary", () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const boundary = new ErrorBoundary({ children: null });
    boundary.componentDidCatch(new Error("sensitive"), {
      componentStack: "sensitive tree",
    });
    expect(log).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });
});
