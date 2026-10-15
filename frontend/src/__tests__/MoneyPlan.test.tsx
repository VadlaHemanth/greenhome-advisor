import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api";
import { MoneyPlan } from "../MoneyPlan";
import type { MoneyPlanResponse, MoneyTariffs } from "../moneyTypes";
import { parseMoneyTariffs, validMoneyPlan } from "../moneyValidation";
import type { Home, RetrofitId } from "../types";
import { deferred, home } from "./fixtures";

// Offline, fictional Task2 contract example; never imported by production.
const selected: RetrofitId[] = ["loft_insulation", "heat_pump"];
const tariffs: MoneyTariffs = {
  electricity_pence: 25,
  gas_pence: 7,
  source: "illustrative",
  as_of: null,
  electricity_standing_before_pence_per_day: null,
  electricity_standing_after_pence_per_day: null,
  gas_standing_before_pence_per_day: null,
  gas_standing_after_pence_per_day: null,
};
const unavailable = { before_gbp: null, after_gbp: null, saving_gbp: null };
const example: MoneyPlanResponse = {
  money: {
    status: "available",
    electricity: { before_gbp: 1200, after_gbp: 1778, saving_gbp: -578 },
    gas: { before_gbp: 840, after_gbp: 168, saving_gbp: 672 },
    total: { before_gbp: 2040, after_gbp: 1946, saving_gbp: 94 },
    monthly_average_gbp: 7.83,
    payback_years: { low: 104.26, high: 176.6 },
    cost_gbp: [9800, 16600],
    standing_charge_note:
      "Electricity and gas standing charges excluded; unchanged charges assumed, not zero. Gas use is retained; no standing-charge removal is inferred from a heat pump.",
  },
  packages: [
    {
      id: "loft_insulation",
      retrofits: ["loft_insulation"],
      cost_gbp: [800, 1600],
      net_saving_kwh: 1440,
      improvement_percent: 8.571428571428571,
      carbon_reduction_kgco2e: 262.5264,
      money_saving_gbp: 100.8,
      recommendation_reason:
        "Largest positive annual bill saving among compared packages.",
    },
    {
      id: "heat_pump",
      retrofits: ["heat_pump"],
      cost_gbp: [9000, 15000],
      net_saving_kwh: 6880,
      improvement_percent: 40.95238095238095,
      carbon_reduction_kgco2e: 1393.9648,
      money_saving_gbp: -8,
      recommendation_reason:
        "Estimated bills increase; the signed loss is retained.",
    },
    {
      id: "loft_insulation+heat_pump",
      retrofits: selected,
      cost_gbp: [9800, 16600],
      net_saving_kwh: 7288,
      improvement_percent: 43.38095238095238,
      carbon_reduction_kgco2e: 1447.3964799999999,
      money_saving_gbp: 94,
      recommendation_reason:
        "Largest known purchased-energy percentage reduction.",
    },
  ],
  picks: {
    energy: "loft_insulation+heat_pump",
    bills: "loft_insulation",
    lowest_cost: "loft_insulation",
  },
  tariffs,
  warnings: ["Fictional demonstration; not measured household savings."],
};

function response(): MoneyPlanResponse {
  return structuredClone(example);
}
function incomplete(): MoneyPlanResponse {
  const result = response();
  result.money.status = "partial";
  result.money.gas = { ...unavailable };
  result.money.total = { ...unavailable };
  result.money.monthly_average_gbp = null;
  result.money.payback_years = null;
  result.tariffs.gas_pence = null;
  result.tariffs.source = "user_entered";
  result.packages.forEach((item) => {
    item.money_saving_gbp = null;
  });
  result.picks.bills = null;
  return result;
}
function changeRate(fuel: "Electricity" | "Gas", value: string) {
  fireEvent.change(
    screen.getByRole("textbox", { name: `${fuel} unit rate (p/kWh)` }),
    {
      target: { value },
    },
  );
}
function calculate() {
  fireEvent.click(screen.getByRole("button", { name: "Calculate" }));
}
function preset() {
  fireEvent.click(
    screen.getByRole("button", { name: /Use illustrative 25p.*7p preset/ }),
  );
}
function table() {
  return screen.getByRole("table", {
    name: "Annual energy costs for your selected plan (GBP)",
  });
}
function renderPlan(
  props: Partial<{
    home: Home;
    selected: RetrofitId[];
    onChange: (ids: RetrofitId[]) => void;
  }> = {},
) {
  return render(
    <MoneyPlan home={home} selected={selected} onChange={vi.fn()} {...props} />,
  );
}

beforeEach(() => {
  vi.spyOn(api, "request").mockResolvedValue(response());
});

describe("MoneyPlan tariff entry and outputs", () => {
  it("starts blank, makes no request and explains null, source, date and standing charges", () => {
    renderPlan();
    for (const fuel of ["Electricity", "Gas"]) {
      const input = screen.getByRole("textbox", {
        name: `${fuel} unit rate (p/kWh)`,
      });
      expect(input).toHaveProperty("value", "");
      const hints = input.getAttribute("aria-describedby")?.split(" ") ?? [];
      expect(hints.length).toBeGreaterThan(0);
      expect(hints.every((id) => document.getElementById(id))).toBe(true);
    }
    expect(screen.getByLabelText("Rate date (optional)")).toHaveProperty(
      "value",
      "",
    );
    expect(screen.getByText("User-entered rates")).toBeTruthy();
    expect(screen.getByText(/No date entered/)).toBeTruthy();
    expect(screen.getByText(/Blank means unknown/)).toBeTruthy();
    expect(
      screen.getByText(/Standing charges are excluded.*assumed unchanged/),
    ).toBeTruthy();
    expect(api.request).not.toHaveBeenCalled();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("sends the complete home, explicit empty selection, rates and date only on Calculate", async () => {
    const result = response();
    result.tariffs = {
      ...tariffs,
      source: "user_entered",
      as_of: "2026-10-15",
    };
    vi.mocked(api.request).mockResolvedValue(result);
    renderPlan({ selected: [] });
    changeRate("Electricity", "25");
    changeRate("Gas", "7");
    fireEvent.change(screen.getByLabelText("Rate date (optional)"), {
      target: { value: "2026-10-15" },
    });
    expect(api.request).not.toHaveBeenCalled();
    calculate();
    await screen.findByRole("table", {
      name: "Annual energy costs for your selected plan (GBP)",
    });
    expect(api.request).toHaveBeenCalledWith(
      "/money-plan",
      { home, selected_retrofits: [], tariffs: result.tariffs },
      expect.any(AbortSignal),
    );
    expect(screen.getByText("15 October 2026")).toBeTruthy();
    expect(screen.getByText(/No improvements selected/)).toBeTruthy();
  });

  it("explicitly applies illustrative 25p/7p, preserves signed fuel amounts and labels monthly average correctly", async () => {
    renderPlan();
    preset();
    await screen.findByRole("table", {
      name: "Annual energy costs for your selected plan (GBP)",
    });
    expect(api.request).toHaveBeenCalledWith(
      "/money-plan",
      { home, selected_retrofits: selected, tariffs },
      expect.any(AbortSignal),
    );
    const costs = within(table());
    const electricity = within(costs.getByRole("row", { name: /Electricity/ }));
    expect(electricity.getByText("£1,200.00")).toBeTruthy();
    expect(electricity.getByText("£1,778.00")).toBeTruthy();
    expect(electricity.getByText("-£578.00")).toBeTruthy();
    expect(costs.getByText("+£672.00")).toBeTruthy();
    expect(costs.getByText("£2,040.00")).toBeTruthy();
    expect(costs.getByText("£1,946.00")).toBeTruthy();
    expect(costs.getByText("+£94.00")).toBeTruthy();
    expect(screen.getByText("+£7.83")).toBeTruthy();
    expect(screen.getByText(/Monthly average saving/)).toBeTruthy();
    expect(
      screen.getByText(
        /annual saving divided by 12.*not a predicted monthly bill/i,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(/Illustrative rates.*not current tariffs/i),
    ).toBeTruthy();
    expect(screen.getByText("104.26–176.60 years")).toBeTruthy();
    expect(
      screen.getByText(/excludes financing.*export revenue/i),
    ).toBeTruthy();
    expect(screen.getByText(example.warnings[0])).toBeTruthy();
    expect(screen.getByText(example.money.standing_charge_note)).toBeTruthy();
    expect(
      screen.getByText(/not installer quotes or savings guarantees/i),
    ).toBeTruthy();
  });

  it("hides results immediately on editing a rate, changes provenance and waits for Calculate", async () => {
    renderPlan();
    preset();
    await screen.findByRole("table", {
      name: "Annual energy costs for your selected plan (GBP)",
    });
    changeRate("Electricity", "0");
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText("+£7.83")).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Use this package" }),
    ).toBeNull();
    expect(screen.getByText("User-entered rates")).toBeTruthy();
    expect(api.request).toHaveBeenCalledTimes(1);
    calculate();
    await waitFor(() => expect(api.request).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.request).mock.calls[1][1]).toEqual({
      home,
      selected_retrofits: selected,
      tariffs: { ...tariffs, electricity_pence: 0, source: "user_entered" },
    });
  });

  it("preserves a missing rate as null and keeps known fuel costs while totals and bill picks abstain", async () => {
    vi.mocked(api.request).mockResolvedValue(incomplete());
    renderPlan();
    changeRate("Electricity", "25");
    calculate();
    await screen.findByRole("table", {
      name: "Annual energy costs for your selected plan (GBP)",
    });
    expect(vi.mocked(api.request).mock.calls[0][1]).toMatchObject({
      tariffs: {
        electricity_pence: 25,
        gas_pence: null,
        source: "user_entered",
        as_of: null,
      },
    });
    expect(within(table()).getByText("£1,778.00")).toBeTruthy();
    const gasRow = within(table()).getByRole("row", { name: /Gas/ });
    expect(within(gasRow).getAllByText("Unavailable")).toHaveLength(3);
    const totalRow = within(table()).getByRole("row", { name: /Total/ });
    expect(within(totalRow).getAllByText("Unavailable")).toHaveLength(3);
    expect(
      screen.getByText(/Both annual fuel readings and both unit rates/),
    ).toBeTruthy();
    expect(
      within(
        screen.getByRole("article", { name: "Strongest bill saving" }),
      ).queryByRole("button"),
    ).toBeNull();
  });

  it("renders missing fuel readings as unavailable even with both rates supplied", async () => {
    const result = incomplete();
    result.tariffs = { ...tariffs };
    vi.mocked(api.request).mockResolvedValue(result);
    renderPlan({ home: { ...home, gas_kwh: null } });
    preset();
    await screen.findByRole("table", {
      name: "Annual energy costs for your selected plan (GBP)",
    });
    expect(
      within(within(table()).getByRole("row", { name: /Total/ })).getAllByText(
        "Unavailable",
      ),
    ).toHaveLength(3);
    expect(screen.queryByText("+£7.83")).toBeNull();
  });

  it("allows both explicit zero rates and renders actual zero money rather than defaults", async () => {
    const result = response();
    for (const fuel of ["electricity", "gas", "total"] as const) {
      result.money[fuel] = { before_gbp: 0, after_gbp: 0, saving_gbp: 0 };
    }
    result.money.monthly_average_gbp = 0;
    result.money.payback_years = null;
    result.tariffs = {
      ...tariffs,
      electricity_pence: 0,
      gas_pence: 0,
      source: "user_entered",
    };
    result.packages.forEach((item) => {
      item.money_saving_gbp = 0;
    });
    result.picks.bills = null;
    vi.mocked(api.request).mockResolvedValue(result);
    renderPlan();
    changeRate("Electricity", "0");
    changeRate("Gas", "0");
    calculate();
    await screen.findByRole("table", {
      name: "Annual energy costs for your selected plan (GBP)",
    });
    expect(within(table()).getAllByText("£0.00")).toHaveLength(9);
    expect(vi.mocked(api.request).mock.calls[0][1]).toMatchObject({
      tariffs: { electricity_pence: 0, gas_pence: 0 },
    });
  });

  it.each(["-1", "200.01", "Infinity", "NaN", "abc", "1e309"])(
    "rejects invalid rate %s with an accessible error and no request",
    (value) => {
      renderPlan();
      changeRate("Electricity", value);
      calculate();
      const input = screen.getByRole("textbox", {
        name: "Electricity unit rate (p/kWh)",
      });
      expect(input.getAttribute("aria-invalid")).toBe("true");
      expect(screen.getByRole("alert").textContent).toMatch(/0.*200/);
      expect(input.getAttribute("aria-describedby")).toContain(
        screen.getByRole("alert").id,
      );
      expect(api.request).not.toHaveBeenCalled();
    },
  );

  it("accepts fractional pence and the inclusive upper bound", async () => {
    renderPlan();
    changeRate("Electricity", "200");
    changeRate("Gas", "0.125");
    calculate();
    await waitFor(() => expect(api.request).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.request).mock.calls[0][1]).toMatchObject({
      tariffs: { electricity_pence: 200, gas_pence: 0.125 },
    });
  });

  it("shows negative total and monthly savings without positive payback", async () => {
    const result = response();
    result.money.electricity = {
      before_gbp: 1200,
      after_gbp: 1880,
      saving_gbp: -680,
    };
    result.money.total = { before_gbp: 2040, after_gbp: 2048, saving_gbp: -8 };
    result.money.monthly_average_gbp = -0.67;
    result.money.payback_years = null;
    result.money.cost_gbp = [9000, 15000];
    vi.mocked(api.request).mockResolvedValue(result);
    renderPlan({ selected: ["heat_pump"] });
    preset();
    await screen.findByRole("table", {
      name: "Annual energy costs for your selected plan (GBP)",
    });
    expect(within(table()).getByText("-£8.00")).toBeTruthy();
    expect(screen.getByText("-£0.67")).toBeTruthy();
    expect(
      screen.getByText(/Negative savings mean higher estimated bills/),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Payback is unavailable without positive annual bill savings/,
      ),
    ).toBeTruthy();
    expect(
      within(
        screen.getByRole("region", { name: "Your selected plan" }),
      ).getByText("£9,000.00–£15,000.00"),
    ).toBeTruthy();
  });
});

describe("MoneyPlan server packages and async isolation", () => {
  it("renders named server picks and only calls onChange when Use this package is clicked", async () => {
    const onChange = vi.fn();
    renderPlan({ onChange });
    preset();
    await screen.findByRole("table", {
      name: "Annual energy costs for your selected plan (GBP)",
    });
    const energy = within(
      screen.getByRole("article", { name: "Largest energy reduction" }),
    );
    const bills = within(
      screen.getByRole("article", { name: "Strongest bill saving" }),
    );
    const cheapest = within(
      screen.getByRole("article", { name: "Lowest upfront cost" }),
    );
    expect(
      energy.getByText("Loft insulation + Air-source heat pump"),
    ).toBeTruthy();
    expect(bills.getByText("Loft insulation")).toBeTruthy();
    expect(cheapest.getByText("Loft insulation")).toBeTruthy();
    expect(bills.getByText("+£100.80 / year")).toBeTruthy();
    expect(
      energy.getByText(example.packages[2].recommendation_reason),
    ).toBeTruthy();
    fireEvent.click(bills.getByRole("button", { name: "Use this package" }));
    expect(onChange).toHaveBeenCalledExactlyOnceWith(["loft_insulation"]);
    expect(api.request).toHaveBeenCalledTimes(1);
    expect(within(table()).getByText("+£94.00")).toBeTruthy();
    expect(screen.queryByText(/saved successfully/i)).toBeNull();
  });

  it("keeps loss-making alternatives inspectable and null picks have no apply button", async () => {
    const result = response();
    result.picks.bills = null;
    result.packages = [result.packages[1]];
    result.picks.energy = "heat_pump";
    result.picks.lowest_cost = "heat_pump";
    vi.mocked(api.request).mockResolvedValue(result);
    renderPlan();
    preset();
    await screen.findByRole("table", {
      name: "Annual energy costs for your selected plan (GBP)",
    });
    expect(screen.getAllByText("-£8.00 / year").length).toBeGreaterThan(0);
    expect(
      within(
        screen.getByRole("article", { name: "Strongest bill saving" }),
      ).queryByRole("button"),
    ).toBeNull();
  });

  it("shows no feasible packages without inventing a cheapest unchanged-home option", async () => {
    const result = response();
    result.packages = [];
    result.picks = { energy: null, bills: null, lowest_cost: null };
    vi.mocked(api.request).mockResolvedValue(result);
    renderPlan({ selected: [] });
    preset();
    await screen.findByRole("table", {
      name: "Annual energy costs for your selected plan (GBP)",
    });
    expect(screen.getByText(/No feasible nonempty packages/)).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Use this package" }),
    ).toBeNull();
  });

  it.each([
    ["budget", { budget_gbp: 17000 }],
    ["permissions", { consent_confirmed: true }],
    ["exclusions", { excluded_retrofits: ["solar_pv"] }],
    ["energy", { electricity_kwh: 6000 }],
    ["physical facts", { floor_area_m2: 120 }],
    ["assumptions", { heat_pump_spf: 4 }],
    ["identity", { property_id: "ANOTHER-HOME" }],
  ] as [string, Partial<Home>][])(
    "keys requests by the full home including %s and discards late responses",
    async (_name, patch) => {
      const old = deferred<MoneyPlanResponse>();
      const next = deferred<MoneyPlanResponse>();
      vi.mocked(api.request)
        .mockReturnValueOnce(old.promise)
        .mockReturnValueOnce(next.promise);
      const onChange = vi.fn();
      const { rerender } = renderPlan({ onChange });
      preset();
      await waitFor(() => expect(api.request).toHaveBeenCalledTimes(1));
      const signal = vi.mocked(api.request).mock.calls[0][2];
      rerender(
        <MoneyPlan
          home={{ ...home, ...patch }}
          selected={selected}
          onChange={onChange}
        />,
      );
      expect(screen.queryByRole("table")).toBeNull();
      await waitFor(() => expect(api.request).toHaveBeenCalledTimes(2));
      expect(signal?.aborted).toBe(true);
      expect(vi.mocked(api.request).mock.calls[1][1]).toMatchObject({
        home: { ...home, ...patch },
      });
      await act(async () => {
        old.resolve(response());
      });
      expect(screen.queryByRole("table")).toBeNull();
      await act(async () => {
        next.resolve(response());
      });
      expect(table()).toBeTruthy();
    },
  );

  it("immediately hides completed results on selection changes and requests the new explicit selection", async () => {
    const next = deferred<MoneyPlanResponse>();
    vi.mocked(api.request)
      .mockResolvedValueOnce(response())
      .mockReturnValueOnce(next.promise);
    const { rerender } = renderPlan();
    preset();
    await screen.findByRole("table", {
      name: "Annual energy costs for your selected plan (GBP)",
    });
    rerender(<MoneyPlan home={home} selected={[]} onChange={vi.fn()} />);
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText("+£7.83")).toBeNull();
    await waitFor(() => expect(api.request).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.request).mock.calls[1][1]).toMatchObject({
      selected_retrofits: [],
    });
  });

  it("cancels an in-flight calculation when a tariff is edited and ignores its eventual resolution", async () => {
    const pending = deferred<MoneyPlanResponse>();
    vi.mocked(api.request).mockReturnValue(pending.promise);
    renderPlan();
    preset();
    await waitFor(() => expect(api.request).toHaveBeenCalledTimes(1));
    changeRate("Gas", "");
    expect(vi.mocked(api.request).mock.calls[0][2]?.aborted).toBe(true);
    await act(async () => {
      pending.resolve(response());
    });
    expect(screen.queryByRole("table")).toBeNull();
    expect(api.request).toHaveBeenCalledTimes(1);
  });

  it("date edits invalidate results and requests with otherwise identical values are not repeated", async () => {
    const { rerender } = renderPlan();
    preset();
    await screen.findByRole("table", {
      name: "Annual energy costs for your selected plan (GBP)",
    });
    rerender(
      <MoneyPlan
        home={{ ...home }}
        selected={[...selected]}
        onChange={vi.fn()}
      />,
    );
    expect(api.request).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText("Rate date (optional)"), {
      target: { value: "2026-10-14" },
    });
    expect(screen.queryByRole("table")).toBeNull();
    expect(api.request).toHaveBeenCalledTimes(1);
  });

  it("resets rates on a parent-provided per-home mount key and aborts outstanding work", async () => {
    const pending = deferred<MoneyPlanResponse>();
    vi.mocked(api.request).mockReturnValue(pending.promise);
    const { rerender } = render(
      <MoneyPlan
        key="first"
        home={home}
        selected={selected}
        onChange={vi.fn()}
      />,
    );
    preset();
    await waitFor(() => expect(api.request).toHaveBeenCalledTimes(1));
    rerender(
      <MoneyPlan
        key="second"
        home={{ ...home, property_id: "NEXT" }}
        selected={[]}
        onChange={vi.fn()}
      />,
    );
    expect(vi.mocked(api.request).mock.calls[0][2]?.aborted).toBe(true);
    expect(
      screen.getByRole("textbox", { name: "Electricity unit rate (p/kWh)" }),
    ).toHaveProperty("value", "");
    await act(async () => {
      pending.resolve(response());
    });
    expect(screen.queryByRole("table")).toBeNull();
    expect(api.request).toHaveBeenCalledTimes(1);
  });

  it("fails closed on malformed money JSON and supports an explicit same-input retry", async () => {
    vi.mocked(api.request)
      .mockResolvedValueOnce({ ...response(), picks: { energy: "invented" } })
      .mockResolvedValueOnce(response());
    renderPlan();
    preset();
    expect((await screen.findByRole("alert")).textContent).toMatch(
      /incomplete.*response/i,
    );
    expect(screen.queryByRole("table")).toBeNull();
    calculate();
    await screen.findByRole("table", {
      name: "Annual energy costs for your selected plan (GBP)",
    });
    expect(api.request).toHaveBeenCalledTimes(2);
  });

  it("rejects a structurally valid response echoing different rates", async () => {
    const result = response();
    result.tariffs.gas_pence = 8;
    vi.mocked(api.request).mockResolvedValue(result);
    renderPlan();
    preset();
    expect((await screen.findByRole("alert")).textContent).toMatch(
      /different.*rates/i,
    );
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows a request error without falling back to a previous result", async () => {
    vi.mocked(api.request)
      .mockResolvedValueOnce(response())
      .mockRejectedValueOnce(
        new api.ApiError(
          "The calculation service is unavailable.",
          503,
          "unavailable",
        ),
      );
    renderPlan();
    preset();
    await screen.findByRole("table", {
      name: "Annual energy costs for your selected plan (GBP)",
    });
    calculate();
    expect(screen.queryByRole("table")).toBeNull();
    expect((await screen.findByRole("alert")).textContent).toMatch(
      /service is unavailable/,
    );
    expect(screen.queryByText("+£7.83")).toBeNull();
  });
});

describe("money contract validation", () => {
  it("accepts Task2 available and partial outputs with signed values", () => {
    expect(validMoneyPlan(response())).toBe(true);
    expect(validMoneyPlan(incomplete())).toBe(true);
  });

  it("accepts fully unavailable money and preserves installation/energy comparisons", () => {
    const result = incomplete();
    result.money.electricity = { ...unavailable };
    result.money.status = "unavailable";
    result.tariffs.electricity_pence = null;
    expect(validMoneyPlan(result)).toBe(true);
  });

  it.each([
    [
      "numeric string",
      (r: MoneyPlanResponse) => {
        (r.money.total as unknown as Record<string, unknown>).saving_gbp = "94";
      },
    ],
    [
      "NaN",
      (r: MoneyPlanResponse) => {
        r.money.gas.after_gbp = NaN;
      },
    ],
    [
      "negative cost",
      (r: MoneyPlanResponse) => {
        r.money.electricity.before_gbp = -1;
      },
    ],
    [
      "infinite package output",
      (r: MoneyPlanResponse) => {
        r.packages[0].net_saving_kwh = Infinity;
      },
    ],
    [
      "unknown retrofit",
      (r: MoneyPlanResponse) => {
        r.packages[0].retrofits = ["unknown" as RetrofitId];
      },
    ],
    [
      "duplicate retrofit",
      (r: MoneyPlanResponse) => {
        r.packages[0].retrofits.push("loft_insulation");
      },
    ],
    [
      "invalid package ID",
      (r: MoneyPlanResponse) => {
        r.packages[0].id = "invented";
      },
    ],
    [
      "duplicate package",
      (r: MoneyPlanResponse) => {
        r.packages.push(r.packages[0]);
      },
    ],
    [
      "missing pick reference",
      (r: MoneyPlanResponse) => {
        r.picks.energy = "unknown";
      },
    ],
    [
      "reversed costs",
      (r: MoneyPlanResponse) => {
        r.money.cost_gbp = [20, 10];
      },
    ],
    [
      "reversed payback",
      (r: MoneyPlanResponse) => {
        r.money.payback_years = { low: 2, high: 1 };
      },
    ],
    [
      "negative payback",
      (r: MoneyPlanResponse) => {
        r.money.payback_years = { low: -1, high: 1 };
      },
    ],
    [
      "unearned payback",
      (r: MoneyPlanResponse) => {
        r.money.total.saving_gbp = -8;
      },
    ],
    [
      "incorrect status",
      (r: MoneyPlanResponse) => {
        r.money.status = "partial";
      },
    ],
    [
      "missing gas but known totals",
      (r: MoneyPlanResponse) => {
        r.money.gas = { ...unavailable };
      },
    ],
    [
      "unrecognised provenance",
      (r: MoneyPlanResponse) => {
        r.tariffs.source = "current" as "illustrative";
      },
    ],
    [
      "invalid date",
      (r: MoneyPlanResponse) => {
        r.tariffs.as_of = "2026-02-30";
      },
    ],
    [
      "rate outside range",
      (r: MoneyPlanResponse) => {
        r.tariffs.gas_pence = 201;
      },
    ],
    [
      "invalid standing charge",
      (r: MoneyPlanResponse) => {
        r.tariffs.gas_standing_after_pence_per_day = 1001;
      },
    ],
    [
      "malformed warnings",
      (r: MoneyPlanResponse) => {
        r.warnings = [null as unknown as string];
      },
    ],
  ] as const)("rejects %s", (_name, mutate) => {
    const result = response();
    mutate(result);
    expect(validMoneyPlan(result)).toBe(false);
  });

  it.each([
    null,
    undefined,
    [],
    {},
    { money: null },
    { money: {}, packages: [null] },
  ])("does not throw on malformed nested input %#", (value) => {
    expect(validMoneyPlan(value)).toBe(false);
  });

  it("rejects invented aggregate amounts on a partial response", () => {
    for (const field of ["monthly_average_gbp", "payback_years"] as const) {
      const result = incomplete();
      if (field === "monthly_average_gbp") result.money[field] = 0;
      else result.money[field] = { low: 0, high: 0 };
      expect(validMoneyPlan(result)).toBe(false);
    }
    const result = incomplete();
    result.packages[0].money_saving_gbp = 1;
    expect(validMoneyPlan(result)).toBe(false);
  });

  it("parses empty/zero/fractional tariffs without imputation and validates real calendar dates", () => {
    const draft = {
      electricity_pence: "0",
      gas_pence: " ",
      as_of: "",
      source: "user_entered" as const,
    };
    expect(parseMoneyTariffs(draft).tariffs).toEqual({
      ...tariffs,
      electricity_pence: 0,
      gas_pence: null,
      source: "user_entered",
    });
    expect(
      parseMoneyTariffs({ ...draft, gas_pence: "7.125", as_of: "2024-02-29" })
        .tariffs?.gas_pence,
    ).toBe(7.125);
    for (const as_of of [
      "2026-02-29",
      "2026-13-01",
      "0000-01-01",
      "2026-10-15T00:00:00Z",
      "not-a-date",
    ]) {
      expect(parseMoneyTariffs({ ...draft, as_of }).tariffs).toBeNull();
      expect(parseMoneyTariffs({ ...draft, as_of }).errors.as_of).toBeTruthy();
    }
  });
});
