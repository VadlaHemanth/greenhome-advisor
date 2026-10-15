import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Reports } from "../Reports";
import * as client from "../api";
import { assessment, home } from "./fixtures";
import type { Metrics } from "../types";

const metrics: Metrics = {
  status: "available",
  metrics: {
    energy: {
      electricity: {
        validation: {
          model: { mae: 1234.5, rmse: 2345.6, n: 300 },
          dummy_median: { mae: 1500.2, rmse: 2600.1, n: 300 },
        },
      },
    },
    synthetic_value: {
      validation: {
        p50_percent: { mae: 0.456, n: 100 },
        dummy_median_percent: { mae: 0.678, n: 100 },
        p50_gbp: { mae: 1234, n: 100 },
        coverage_p10_p90_active_scenarios: 0.75,
      },
    },
  },
};

describe("actual report payloads", () => {
  it("distinguishes source quality without replacing or inventing source links", async () => {
    vi.spyOn(client.api, "metrics").mockResolvedValue({
      status: "unavailable",
      metrics: null,
    });
    render(<Reports home={home} assessment={assessment} />);
    fireEvent.click(screen.getByText("Where the numbers come from"));
    expect(
      screen.getByText("Government data: consumption benchmark"),
    ).toBeTruthy();
    expect(
      screen.getByText("Scenario assumptions: retrofit savings/costs"),
    ).toBeTruthy();
    expect(screen.getByText("Synthetic illustration: value only")).toBeTruthy();
    expect(screen.getByText(/Not every input is government data/)).toBeTruthy();
    expect(screen.queryByText(/3.21%/)).toBeNull();
    for (const source of assessment.sources) {
      expect(
        screen.getByRole("link", { name: new RegExp(source.label) }),
      ).toHaveProperty("href", source.url);
    }
    await screen.findByText(/Training results are unavailable/);
  });
  it("renders metric values from the supplied API payload, not component constants", async () => {
    vi.spyOn(client.api, "metrics").mockResolvedValue(metrics);
    render(<Reports home={home} assessment={assessment} />);
    expect(await screen.findByText("1,234.5")).toBeTruthy();
    expect(screen.getByText("1,500.2")).toBeTruthy();
    expect(screen.getByText("0.456")).toBeTruthy();
    expect(screen.getByText("0.750")).toBeTruthy();
    expect(screen.getByText(/not calibrated to market prices/)).toBeTruthy();
  });
  it("downloads the exact metric object", async () => {
    vi.spyOn(client.api, "metrics").mockResolvedValue(metrics);
    const download = vi
      .spyOn(client, "downloadJson")
      .mockImplementation(() => {});
    render(<Reports home={home} assessment={assessment} />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: /Download actual metrics JSON/,
      }),
    );
    expect(download).toHaveBeenCalledWith(
      "greenhome-training-metrics.json",
      metrics,
    );
  });
  it("downloads the current engine assessment with its warnings and missing model outputs", async () => {
    vi.spyOn(client.api, "metrics").mockResolvedValue({
      status: "unavailable",
      metrics: null,
    });
    const download = vi
      .spyOn(client, "downloadJson")
      .mockImplementation(() => {});
    render(<Reports home={home} assessment={assessment} />);
    fireEvent.click(screen.getByRole("button", { name: /^Download JSON$/ }));
    expect(download).toHaveBeenCalledWith(
      "greenhome-assessment.json",
      expect.objectContaining({ assessment }),
    );
  });
  it("does not offer an assessment export while the current plan is invalid or absent", async () => {
    vi.spyOn(client.api, "metrics").mockResolvedValue({
      status: "unavailable",
      metrics: null,
    });
    render(<Reports home={home} assessment={null} />);
    expect(
      screen.getByRole("button", { name: /^Download JSON$/ }),
    ).toHaveProperty("disabled", true);
    expect(
      await screen.findByText(/No sample counts, errors or accuracy values/),
    ).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });
  it("has an explicit retry action when metrics fail", async () => {
    const load = vi
      .spyOn(client.api, "metrics")
      .mockRejectedValueOnce(
        new client.ApiError("Metrics unavailable", 500, "failed"),
      )
      .mockResolvedValueOnce(metrics);
    render(<Reports home={home} assessment={null} />);
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Metrics unavailable",
    );
    fireEvent.click(screen.getByRole("button", { name: "Refresh results" }));
    expect(await screen.findByText("1,234.5")).toBeTruthy();
    expect(load).toHaveBeenCalledTimes(2);
  });
});
