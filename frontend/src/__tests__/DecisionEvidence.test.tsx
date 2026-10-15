import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DecisionEvidence } from "../DecisionEvidence";
import { catalogue, decision } from "./fixtures";

describe("decision comparison evidence", () => {
  it("labels nominal, greedy and robust choices and acknowledges identical selections", () => {
    render(<DecisionEvidence decision={decision} catalogue={catalogue} />);
    expect(screen.getByText("Saved assumptions · nominal")).toBeTruthy();
    expect(screen.getByText("Catalogue order · greedy")).toBeTruthy();
    expect(screen.getByText("Tested scenarios · robust")).toBeTruthy();
    expect(
      screen.getByText(/All three approaches return the same package/),
    ).toBeTruthy();
    expect(
      screen.queryByText(/outperforms|uniquely optimal|guaranteed best/i),
    ).toBeNull();
  });

  it("keeps detailed package estimates collapsed and renders exact returned figures when opened", () => {
    render(
      <DecisionEvidence
        catalogue={catalogue}
        decision={{
          ...decision,
          packages: [
            {
              retrofits: ["loft_insulation"],
              cost_gbp: [800, 1600],
              nominal_saving_kwh: 1201.25,
              min_saving_kwh: -25.5,
              max_saving_kwh: 1750.75,
              max_regret_kwh: 125.3,
              nominal_carbon_kgco2e: 100,
            },
          ],
        }}
      />,
    );
    const summary = screen.getByText("Compare tested package estimates");
    expect(summary.closest("details")).toHaveProperty("open", false);
    fireEvent.click(summary);
    expect(summary.closest("details")).toHaveProperty("open", true);
    const table = screen.getByRole("table", {
      name: "Package estimates across tested scenarios",
    });
    expect(within(table).getByText("£800–£1,600")).toBeTruthy();
    expect(within(table).getByText("+1,201.3")).toBeTruthy();
    expect(within(table).getByText("-25.5")).toBeTruthy();
    expect(within(table).getByText("+1,750.8")).toBeTruthy();
    expect(within(table).getByText("125.3")).toBeTruthy();
  });

  it("distinguishes unavailable methods from a valid empty package", () => {
    render(
      <DecisionEvidence
        catalogue={catalogue}
        decision={{
          ...decision,
          nominal_package: null,
          recommended_package: [],
          packages: null,
        }}
      />,
    );
    expect(screen.getByText("Unavailable")).toBeTruthy();
    expect(screen.getByText("No improvements selected")).toBeTruthy();
    fireEvent.click(screen.getByText("Compare tested package estimates"));
    expect(
      screen.getByText(/Package-level evidence is unavailable/),
    ).toBeTruthy();
  });
});
