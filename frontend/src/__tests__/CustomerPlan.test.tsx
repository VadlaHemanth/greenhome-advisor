import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { CustomerPlan } from "../CustomerPlan";
import { assessment, home } from "./fixtures";
import { workspace } from "./workspaceFixtures";

it("prints signed engine values, package, costs and visible warnings without evaluation metrics", () => {
  const print = vi.spyOn(window, "print").mockImplementation(() => {});
  render(
    <CustomerPlan
      home={{ ...home, excluded_retrofits: ["solar_pv"] }}
      assessment={assessment}
      selected={["heat_pump"]}
      customer={workspace.customers[0]}
      unsaved
    />,
  );
  expect(screen.getByText("-2,720 kWh/year")).toBeTruthy();
  expect(screen.getByText("£9,000–£15,000")).toBeTruthy();
  expect(screen.getByText("Air-source heat pump")).toBeTruthy();
  expect(screen.getByText("Solar panels")).toBeTruthy();
  expect(screen.getByText(assessment.scenario.warnings[0])).toBeTruthy();
  expect(screen.getByText(assessment.scenario.assumptions[0])).toBeTruthy();
  expect(screen.getByText(/with unsaved draft changes/)).toBeTruthy();
  expect(screen.queryByText("Model MAE")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /Print or save plan/ }));
  expect(print).toHaveBeenCalledOnce();
});
it("disables printing unavailable calculations and does not retain an old result", () => {
  const props = {
    home,
    selected: ["heat_pump"] as const,
    customer: null,
    unsaved: false,
  };
  const { rerender } = render(
    <CustomerPlan
      {...props}
      selected={["heat_pump"]}
      assessment={assessment}
    />,
  );
  rerender(
    <CustomerPlan {...props} selected={["heat_pump"]} assessment={null} />,
  );
  expect(
    screen.getByRole("button", { name: /Print or save plan/ }),
  ).toHaveProperty("disabled", true);
  expect(screen.queryByText("-2,720 kWh/year")).toBeNull();
});
it("retains missing-data and post-completion evidence instructions in the printable document", () => {
  render(
    <CustomerPlan
      home={{
        ...home,
        electricity_kwh: null,
        gas_kwh: null,
        epc_rating: null,
        floor_area_m2: null,
      }}
      assessment={null}
      selected={[]}
      customer={{ ...workspace.customers[0], baseline_status: "needs_update" }}
      unsaved={false}
    />,
  );
  expect(screen.getByText(/Old bills must not be reused/)).toBeTruthy();
  expect(screen.getByText(/Find annual grid electricity/)).toBeTruthy();
  expect(screen.getByText(/Check the recorded EPC rating/)).toBeTruthy();
  expect(screen.getByText(/Confirm floor area/)).toBeTruthy();
});
