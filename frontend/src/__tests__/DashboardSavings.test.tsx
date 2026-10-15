import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Dashboard } from "../Dashboard";
import { ScenarioRail } from "../ScenarioRail";
import type { Assessment } from "../types";
import { assessment, catalogue, home } from "./fixtures";

const noPlan: Assessment = {
  ...assessment,
  selected_retrofits: [],
  scenario: {
    ...assessment.scenario,
    electricity_kwh: 4800,
    gas_kwh: 12000,
    electricity_saving_kwh: 0,
    gas_saving_kwh: 0,
    net_saving_kwh: 0,
    carbon_reduction_kgco2e: 0,
    improvement_percent: 0,
    cost_gbp: [0, 0],
  },
};

function showDashboard(
  plan: Assessment | null,
  options: Partial<Parameters<typeof Dashboard>[0]> = {},
) {
  const props = {
    home,
    baseline: noPlan,
    plan,
    planLoading: false,
    edit: vi.fn(),
    navigate: vi.fn(),
    showScore: vi.fn(),
    showDetails: vi.fn(),
    onChange: vi.fn(),
    ...options,
  };
  render(<Dashboard {...props} />);
  return props;
}

function card(title: string) {
  return screen.getByRole("heading", { name: title }).closest("article")!;
}

describe("dashboard separates an empty plan from calculated savings", () => {
  it("explains unavailable suggestions without presenting no-op arithmetic as opportunity", () => {
    const props = showDashboard(noPlan, { selected: [] });
    expect(card("Suggested energy saving").textContent).toContain(
      "Unavailable",
    );
    expect(card("Operational carbon").textContent).toContain("Unavailable");
    expect(card("Annual energy use").textContent).toContain("16,800");
    expect(screen.getByText("Choose a plan first")).toBeTruthy();
    expect(
      screen.queryByRole("table", { name: /Annual purchased energy/ }),
    ).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: "Choose improvements" }),
    );
    expect(props.navigate).toHaveBeenCalledWith("improvements");
    fireEvent.click(
      screen.getByRole("button", { name: "Add loft insulation" }),
    );
    expect(props.onChange).toHaveBeenCalledWith(["loft_insulation"]);
  });

  it("previews an engine-supplied starting point without silently selecting it", () => {
    const baseline: Assessment = {
      ...noPlan,
      recommendations: [
        {
          ...noPlan.recommendations[0],
          standalone: {
            ...noPlan.scenario,
            net_saving_kwh: 1440,
            gas_saving_kwh: 1440,
            carbon_reduction_kgco2e: 262.5264,
          },
        },
      ],
    };
    const props = showDashboard(noPlan, { baseline, selected: [] });
    expect(card("Suggested energy saving").textContent).toContain("+1,440");
    expect(card("Operational carbon").textContent).toContain("+263");
    expect(screen.getByText("Preview · Loft insulation")).toBeTruthy();
    expect(props.onChange).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Use suggested plan" }));
    expect(props.onChange).toHaveBeenCalledWith(["loft_insulation"]);
  });

  it("keeps missing preview totals unavailable and excludes joint-only zero options", () => {
    const baseline: Assessment = {
      ...noPlan,
      recommendations: [
        { ...noPlan.recommendations[0], standalone: noPlan.scenario },
        {
          ...noPlan.recommendations[1],
          standalone: {
            ...noPlan.scenario,
            net_saving_kwh: null,
            carbon_reduction_kgco2e: null,
          },
        },
      ],
    };
    showDashboard(noPlan, { baseline, selected: [] });
    expect(card("Suggested energy saving").textContent).toContain(
      "Unavailable",
    );
    expect(card("Operational carbon").textContent).toContain("Unavailable");
    expect(screen.queryByText("Preview · Loft insulation")).toBeNull();
    expect(screen.getByText(/More energy readings are needed/)).toBeTruthy();
  });

  it("shows actual engine numbers and preserves a negative fuel saving", () => {
    showDashboard(assessment, { selected: ["heat_pump"] });
    expect(card("Selected energy saving").textContent).toContain("+6,880");
    expect(card("Operational carbon").textContent).toContain("+1,395");
    expect(
      screen.getByRole("row", { name: /Grid electricity/ }).textContent,
    ).toContain("-2,720");
    expect(screen.queryByText("No plan yet")).toBeNull();
  });

  it("keeps a genuine zero when a nonempty selected scenario returns it", () => {
    showDashboard(
      { ...noPlan, selected_retrofits: ["heat_pump"] },
      {
        selected: ["heat_pump"],
      },
    );
    expect(card("Selected energy saving").textContent).toContain("0");
    expect(card("Operational carbon").textContent).toContain("0");
    expect(screen.queryByText("No plan yet")).toBeNull();
  });

  it("does not turn unknown energy or carbon into zero", () => {
    showDashboard(
      {
        ...assessment,
        scenario: {
          ...assessment.scenario,
          net_saving_kwh: null,
          carbon_reduction_kgco2e: null,
          improvement_percent: null,
        },
      },
      { selected: ["heat_pump"] },
    );
    expect(card("Selected energy saving").textContent).toContain("Unavailable");
    expect(card("Operational carbon").textContent).toContain("Unavailable");
  });

  it("shows calculation state rather than stale values while a new selection loads", () => {
    showDashboard(null, { selected: ["loft_insulation"], planLoading: true });
    expect(card("Selected energy saving").textContent).toContain("Calculating");
    expect(card("Operational carbon").textContent).toContain("Calculating");
    expect(
      screen.queryByRole("table", { name: /Annual purchased energy/ }),
    ).toBeNull();
  });
});

describe("scenario rail direct selection", () => {
  function showRail(selected: Parameters<typeof ScenarioRail>[0]["selected"]) {
    const change = vi.fn();
    render(
      <ScenarioRail
        baseline={noPlan}
        assessment={selected.length ? assessment : noPlan}
        selected={selected}
        onChange={change}
        loading={false}
        error={null}
        retry={vi.fn()}
        catalogue={catalogue}
        openImprovements={vi.fn()}
        openQuestions={vi.fn()}
        openDetails={vi.fn()}
      />,
    );
    return change;
  }

  it("explains the empty plan and provides explicitly named add actions", () => {
    const change = showRail([]);
    expect(
      screen.getByRole("heading", { name: "Start with one improvement" }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("heading", { name: "Projected annual changes" }),
    ).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: "Add Loft insulation to plan" }),
    );
    expect(change).toHaveBeenCalledWith(["loft_insulation"]);
  });

  it("shows selected results and removes only the chosen measure", () => {
    const change = showRail(["heat_pump"]);
    expect(
      screen.getByRole("heading", { name: "Projected annual changes" }),
    ).toBeTruthy();
    const button = screen.getByRole("button", {
      name: "Remove Air-source heat pump from plan",
    });
    expect(button.getAttribute("aria-pressed")).toBe("true");
    expect(within(button).getByText("Remove")).toBeTruthy();
    fireEvent.click(button);
    expect(change).toHaveBeenCalledWith([]);
  });
});
