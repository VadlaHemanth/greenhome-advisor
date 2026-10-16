import { useState } from "react";
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
import { DashboardMoney } from "../DashboardMoney";
import { MoneyPlan } from "../MoneyPlan";
import type { MoneyPlanResponse } from "../moneyTypes";
import type { Home, RetrofitId } from "../types";
import { useMoneyPlan } from "../useMoneyPlan";
import { deferred } from "./fixtures";
import {
  moneyHome,
  moneyResponse,
  moneySelected,
  negativeMoney,
  partialMoney,
  unchangedMoney,
  zeroMoney,
} from "./moneyFixtures";

function SharedPages({
  home = moneyHome,
  selected = moneySelected,
  scope = "public",
  both = false,
}: {
  home?: Home | null;
  selected?: RetrofitId[];
  scope?: string;
  both?: boolean;
}) {
  const controller = useMoneyPlan(home, selected, scope);
  const [page, setPage] = useState("dashboard");
  return (
    <>
      {(both || page === "dashboard") && (
        <DashboardMoney
          controller={controller}
          onCompare={() => setPage("costs")}
        />
      )}
      {(both || page === "costs") && home && (
        <>
          <button onClick={() => setPage("dashboard")}>
            Back to dashboard
          </button>
          <MoneyPlan
            home={home}
            selected={selected}
            onChange={vi.fn()}
            controller={controller}
          />
        </>
      )}
    </>
  );
}

const metric = (label: string) =>
  screen.getByText(label, { selector: "dt" }).parentElement!;
const preset = () =>
  fireEvent.click(
    screen.getByRole("button", { name: /Use illustrative 25p.*7p preset/ }),
  );
const changeRate = (fuel: string, value: string) =>
  fireEvent.change(
    screen.getByRole("textbox", { name: `${fuel} unit rate (p/kWh)` }),
    { target: { value } },
  );

beforeEach(() => {
  vi.spyOn(api, "request").mockResolvedValue(moneyResponse());
});

describe("Dashboard money and shared Costs & packages", () => {
  it("does not invent default amounts and identifies the explicit illustrative action", () => {
    render(<SharedPages />);
    expect(
      screen.getByText(/Calculate to compare this home and plan/),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /Use illustrative 25p.*7p preset/ }),
    ).toBeTruthy();
    expect(screen.queryByText("£2,040.00")).toBeNull();
    expect(screen.getByText(/Standing charges are excluded/)).toBeTruthy();
    expect(screen.getByText(/England and Wales/)).toBeTruthy();
    expect(api.request).not.toHaveBeenCalled();
  });

  it("prominently labels before/after, signed annual/monthly savings and installation costs", async () => {
    render(<SharedPages />);
    preset();
    await screen.findByText("+£94.00");
    expect(
      within(metric("Current annual variable cost")).getByText("£2,040.00"),
    ).toBeTruthy();
    expect(
      within(metric("Proposed annual variable cost")).getByText("£1,946.00"),
    ).toBeTruthy();
    expect(
      within(metric("Annual bill saving")).getByText("+£94.00"),
    ).toBeTruthy();
    expect(
      within(metric("Monthly average saving")).getByText("+£7.83"),
    ).toBeTruthy();
    expect(
      within(metric("Indicative installation cost")).getByText(
        "£9,800.00–£16,600.00",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /annual saving divided by 12.*not a predicted monthly bill/i,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(/Illustrative rates.*not current tariffs/),
    ).toBeTruthy();
  });

  it("shares confirmed results and drafts across page unmounts without duplicate requests", async () => {
    render(<SharedPages />);
    preset();
    await screen.findByText("+£94.00");
    fireEvent.click(screen.getByRole("button", { name: /Compare packages/ }));
    const table = screen.getByRole("table", {
      name: "Annual energy costs for your selected plan (GBP)",
    });
    expect(within(table).getByText("+£94.00")).toBeTruthy();
    expect(
      screen.getByRole("textbox", { name: "Gas unit rate (p/kWh)" }),
    ).toHaveProperty("value", "7");
    expect(api.request).toHaveBeenCalledTimes(1);
    changeRate("Gas", "0");
    expect(screen.queryByRole("table")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Back to dashboard" }));
    expect(
      screen.getByRole("textbox", { name: "Gas unit rate (p/kWh)" }),
    ).toHaveProperty("value", "0");
    expect(screen.queryByText("+£94.00")).toBeNull();
    expect(api.request).toHaveBeenCalledTimes(1);
    preset();
    await screen.findByText("+£94.00");
    expect(api.request).toHaveBeenCalledTimes(2);
  });

  it("retains zero without treating unknowns as zero", async () => {
    vi.mocked(api.request).mockResolvedValue(zeroMoney());
    render(<SharedPages />);
    changeRate("Electricity", "0");
    changeRate("Gas", "0");
    fireEvent.click(screen.getByRole("button", { name: "Calculate" }));
    await waitFor(() =>
      expect(
        within(metric("Annual bill saving")).getByText("£0.00"),
      ).toBeTruthy(),
    );
    expect(screen.queryByText("Unavailable")).toBeNull();
    expect(
      screen.getByText(/No change in estimated annual variable costs/),
    ).toBeTruthy();
  });

  it("labels partial results without inventing a total or monthly amount", async () => {
    vi.mocked(api.request).mockResolvedValue(partialMoney());
    render(<SharedPages />);
    changeRate("Electricity", "25");
    fireEvent.click(screen.getByRole("button", { name: "Calculate" }));
    await screen.findByText("Partial estimate");
    expect(
      within(metric("Annual bill saving")).getByText("Unavailable"),
    ).toBeTruthy();
    expect(
      within(metric("Monthly average saving")).getByText("Unavailable"),
    ).toBeTruthy();
    expect(screen.getByText(/missing is not zero/i)).toBeTruthy();
    expect(screen.queryByText("£0.00")).toBeNull();
  });

  it("labels higher bills and retains negative annual/monthly amounts with no payback", async () => {
    vi.mocked(api.request).mockResolvedValue(negativeMoney());
    render(<SharedPages selected={["heat_pump"]} />);
    preset();
    await screen.findByText("-£8.00");
    expect(
      within(metric("Monthly average saving")).getByText("-£0.67"),
    ).toBeTruthy();
    expect(screen.getByText(/higher estimated bills/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Compare packages/ }));
    expect(
      screen.getByText(
        /Payback is unavailable without positive annual bill savings/,
      ),
    ).toBeTruthy();
    expect(api.request).toHaveBeenCalledTimes(1);
  });

  it("identifies no selection instead of claiming an upgrade benefit", async () => {
    vi.mocked(api.request).mockResolvedValue(unchangedMoney());
    render(<SharedPages selected={[]} />);
    expect(screen.getByText(/No improvements selected/)).toBeTruthy();
    preset();
    await waitFor(() =>
      expect(
        within(metric("Annual bill saving")).getByText("£0.00"),
      ).toBeTruthy(),
    );
    expect(
      within(metric("Indicative installation cost")).getByText("£0.00–£0.00"),
    ).toBeTruthy();
    expect(screen.getByText(/No improvements selected/)).toBeTruthy();
  });

  it("resets visible amounts and rates on scope change even for an identical home ID", async () => {
    const { rerender } = render(<SharedPages />);
    preset();
    await screen.findByText("+£94.00");
    rerender(<SharedPages scope="private:other-workspace" />);
    expect(screen.queryByText("+£94.00")).toBeNull();
    expect(screen.queryByText("£2,040.00")).toBeNull();
    expect(
      screen.getByRole("textbox", { name: "Electricity unit rate (p/kWh)" }),
    ).toHaveProperty("value", "");
    expect(api.request).toHaveBeenCalledTimes(1);
  });

  it("shares field errors, focuses the submitted form's invalid field and uses unique accessible IDs", async () => {
    const { container } = render(<SharedPages both />);
    const forms = container.querySelectorAll("form");
    expect(forms).toHaveLength(2);
    const dashboard = within(forms[0]);
    const costs = within(forms[1]);
    fireEvent.change(
      costs.getByRole("textbox", { name: "Gas unit rate (p/kWh)" }),
      { target: { value: "-1" } },
    );
    fireEvent.click(costs.getByRole("button", { name: "Calculate" }));
    const invalid = costs.getByRole("textbox", {
      name: "Gas unit rate (p/kWh)",
    });
    expect(document.activeElement).toBe(invalid);
    expect(invalid.getAttribute("aria-invalid")).toBe("true");
    expect(
      dashboard.getByRole("textbox", { name: "Gas unit rate (p/kWh)" }),
    ).toHaveProperty("value", "-1");
    const ids = [...container.querySelectorAll("[id]")].map(
      (element) => element.id,
    );
    expect(new Set(ids).size).toBe(ids.length);
    for (const input of container.querySelectorAll("input"))
      for (const id of input.getAttribute("aria-describedby")?.split(" ") ?? [])
        expect(document.getElementById(id)).not.toBeNull();
    expect(api.request).not.toHaveBeenCalled();
  });

  it("keeps source/date visible on both pages and clears dates for the explicit preset", async () => {
    const dated = moneyResponse();
    dated.tariffs.source = "user_entered";
    dated.tariffs.as_of = "2026-10-16";
    vi.mocked(api.request)
      .mockResolvedValueOnce(dated)
      .mockResolvedValueOnce(moneyResponse());
    render(<SharedPages />);
    changeRate("Electricity", "25");
    changeRate("Gas", "7");
    fireEvent.change(screen.getByLabelText("Rate date (optional)"), {
      target: { value: "2026-10-16" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Calculate" }));
    await screen.findByText("+£94.00");
    expect(screen.getByText("16 October 2026")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Compare packages/ }));
    expect(screen.getByText("16 October 2026")).toBeTruthy();
    expect(screen.getByText("User-entered rates")).toBeTruthy();
    preset();
    expect(screen.getByLabelText("Rate date (optional)")).toHaveProperty(
      "value",
      "",
    );
    expect(screen.getByText("No date entered")).toBeTruthy();
    await screen.findByRole("table", {
      name: "Annual energy costs for your selected plan (GBP)",
    });
  });

  it("shows loading and retryable errors rather than old values", async () => {
    const next = deferred<MoneyPlanResponse>();
    vi.mocked(api.request)
      .mockResolvedValueOnce(moneyResponse())
      .mockReturnValueOnce(next.promise);
    render(<SharedPages />);
    preset();
    await screen.findByText("+£94.00");
    fireEvent.click(screen.getByRole("button", { name: "Calculate" }));
    expect(screen.queryByText("+£94.00")).toBeNull();
    expect(
      screen.getByText(/Calculating this home and selected plan/),
    ).toBeTruthy();
    await act(async () =>
      next.reject(
        new api.ApiError(
          "Calculation unavailable. Try Calculate again.",
          503,
          "unavailable",
        ),
      ),
    );
    expect(screen.getByRole("alert").textContent).toMatch(
      /Calculation unavailable/,
    );
    expect(screen.queryByText("£2,040.00")).toBeNull();
  });

  it("asks for a home without exposing an active tariff form when home is null", () => {
    render(<SharedPages home={null} />);
    expect(screen.getByText(/Select a home/i)).toBeTruthy();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(api.request).not.toHaveBeenCalled();
  });
});
