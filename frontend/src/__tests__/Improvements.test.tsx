import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Improvements } from "../Improvements";
import { api, ApiError } from "../api";
import type { RetrofitId } from "../types";
import { assessment, deferred, home } from "./fixtures";

function props() {
  return {
    home,
    baseline: assessment,
    selected: ["heat_pump"] as RetrofitId[],
    onChange: vi.fn(),
    showDetails: vi.fn(),
    compareSelected: ["loft_insulation"] as RetrofitId[],
    setCompareSelected: vi.fn(),
  };
}

describe("package comparison interactions", () => {
  it("does not request a comparison until explicitly opened", () => {
    const compare = vi.spyOn(api, "compare");
    render(<Improvements {...props()} />);
    expect(compare).not.toHaveBeenCalled();
  });
  it("compares independent A and B selections and applies B only on request", async () => {
    const compare = vi
      .spyOn(api, "compare")
      .mockResolvedValue({ package_a: assessment, package_b: assessment });
    const input = props();
    render(<Improvements {...input} />);
    fireEvent.click(screen.getByRole("button", { name: "Compare packages" }));
    const use = await screen.findByRole("button", {
      name: "Use Package B as my plan",
    });
    expect(compare).toHaveBeenCalledWith(
      home,
      ["heat_pump"],
      ["loft_insulation"],
      expect.any(AbortSignal),
    );
    expect(input.onChange).not.toHaveBeenCalled();
    fireEvent.click(use);
    expect(input.onChange).toHaveBeenCalledWith(["loft_insulation"]);
  });
  it("clears stale comparison results immediately when B changes", async () => {
    const pending = deferred<{
      package_a: typeof assessment;
      package_b: typeof assessment;
    }>();
    vi.spyOn(api, "compare")
      .mockResolvedValueOnce({ package_a: assessment, package_b: assessment })
      .mockReturnValueOnce(pending.promise);
    const input = props();
    const { rerender } = render(<Improvements {...input} />);
    fireEvent.click(screen.getByRole("button", { name: "Compare packages" }));
    await screen.findByRole("button", { name: "Use Package B as my plan" });
    rerender(<Improvements {...input} compareSelected={[]} />);
    expect(
      screen.queryByRole("button", { name: "Use Package B as my plan" }),
    ).toBeNull();
    await act(async () => {
      pending.reject(new ApiError("Package rejected", 422, "invalid_scenario"));
    });
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      expect.stringContaining("Package rejected"),
    );
    expect(screen.queryByRole("table")).toBeNull();
  });
  it("aborts comparison requests when the panel closes", async () => {
    const pending = deferred<{
      package_a: typeof assessment;
      package_b: typeof assessment;
    }>();
    const compare = vi.spyOn(api, "compare").mockReturnValue(pending.promise);
    render(<Improvements {...props()} />);
    fireEvent.click(screen.getByRole("button", { name: "Compare packages" }));
    await waitFor(() => expect(compare).toHaveBeenCalled());
    const signal = compare.mock.calls[0][3];
    fireEvent.click(screen.getByRole("button", { name: "Close comparison" }));
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      pending.resolve({ package_a: assessment, package_b: assessment });
    });
    expect(screen.queryByRole("table")).toBeNull();
  });
});
