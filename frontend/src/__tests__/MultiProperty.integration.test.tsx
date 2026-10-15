import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { api, ApiError } from "../api";
import type { CanonicalWorkspace, Reply } from "../types";
import { assessment, catalogue, deferred, health } from "./fixtures";
import { multiWorkspace, propertyFixture } from "./multiPropertyFixtures";

let saved: CanonicalWorkspace;
beforeEach(() => {
  saved = multiWorkspace([2, 1, 1, 1]);
  window.history.replaceState(null, "", "#workspace");
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.spyOn(api, "homes").mockResolvedValue(
    saved.customers.map((c, i) => ({
      ...c.properties[0].home,
      property_id: `DEMO-0${i + 1}`,
    })),
  );
  vi.spyOn(api, "catalogue").mockResolvedValue(catalogue);
  vi.spyOn(api, "health").mockResolvedValue(health);
  vi.spyOn(api, "workspace").mockImplementation(async () =>
    structuredClone(saved),
  );
  vi.spyOn(api, "whatIf").mockRejectedValue(
    new Error("No provider calls permitted in this test."),
  );
  vi.spyOn(api, "saveCustomer").mockRejectedValue(
    new Error("v2 must not use legacy save"),
  );
  vi.spyOn(api, "completeRetrofit").mockRejectedValue(
    new Error("v2 must not use legacy completion"),
  );
  vi.spyOn(api, "assess").mockImplementation(async (home, selected) => ({
    ...assessment,
    home,
    selected_retrofits: selected ?? [],
    recommendations: assessment.recommendations.map((r) => ({
      ...r,
      feasible: !home.excluded_retrofits?.includes(r.id),
    })),
  }));
  vi.spyOn(api, "saveProperty").mockImplementation(async (cid, pid, update) => {
    const customer = saved.customers.find((c) => c.id === cid)!;
    const property = customer.properties.find((p) => p.id === pid)!;
    if (
      customer.version !== update.customer_version ||
      property.version !== update.version
    )
      throw new ApiError(
        "Stale customer/property versions",
        409,
        "stale_version",
      );
    const {
      customer_version: _ownerVersion,
      baseline_confirmed_after_completion,
      ...fields
    } = update;
    Object.assign(property, fields, { version: property.version + 1 });
    if (baseline_confirmed_after_completion)
      property.baseline_status = "current";
    customer.version += 1;
    return structuredClone(saved);
  });
  vi.spyOn(api, "addProperty").mockImplementation(async (cid) => {
    const customer = saved.customers.find((c) => c.id === cid)!;
    const property = propertyFixture(cid, customer.properties.length + 1);
    property.preferences = {
      budget_gbp: null,
      deferred_retrofits: [],
      priority: "energy",
      disruption: "flexible",
    };
    property.home.budget_gbp = null;
    property.selected_retrofits = [];
    customer.properties.push(property);
    customer.version += 1;
    return structuredClone(saved);
  });
  vi.spyOn(api, "saveCustomerSettings").mockImplementation(
    async (cid, update) => {
      const customer = saved.customers.find((c) => c.id === cid)!;
      Object.assign(customer, update, { version: customer.version + 1 });
      return structuredClone(saved);
    },
  );
  vi.spyOn(api, "completeProperty").mockImplementation(
    async (cid, pid, event) => {
      const customer = saved.customers.find((c) => c.id === cid)!;
      const property = customer.properties.find((p) => p.id === pid)!;
      property.selected_retrofits = [];
      property.baseline_status = "needs_update";
      property.home.insulation = "good";
      property.home.electricity_kwh = null;
      property.home.gas_kwh = null;
      property.events.push({
        id: `event-${pid}`,
        kind: event.kind,
        retrofit_id: event.retrofit_id,
        completed_on: event.completed_on,
        created_at: "2026-10-11T00:00:00Z",
        planning_cost_upper_gbp: 1600,
      });
      property.version += 1;
      customer.version += 1;
      customer.budget_summary = {
        planned_upper_gbp: 0,
        completed_reserved_gbp: 1600,
        total_reserved_gbp: 1600,
        remaining_gbp: null,
        status: "unlimited",
      };
      return structuredClone(saved);
    },
  );
});
async function mount() {
  const view = render(<App />);
  await screen.findByRole("heading", {
    name: /Customer settings · Example customer 1/,
  });
  await waitFor(() =>
    expect(screen.getByRole("combobox", { name: "Customer" })).toHaveProperty(
      "disabled",
      false,
    ),
  );
  return view;
}
function propertySelect(index: number) {
  fireEvent.change(screen.getByRole("combobox", { name: "Property" }), {
    target: { value: `customer-1-property-${index}` },
  });
}
function budget(value: string) {
  fireEvent.change(
    screen.getByRole("spinbutton", { name: "Property active-plan budget (£)" }),
    { target: { value } },
  );
}
function nav(name: string) {
  fireEvent.click(
    within(
      screen.getByRole("navigation", { name: "Main navigation" }),
    ).getByRole("link", { name }),
  );
}

describe("canonical property ownership in the UI", () => {
  it.each([1, 2, 4])(
    "shows separate selectors and only the owner's %i properties; never promotes roots",
    async (count) => {
      saved = multiWorkspace([count, 1, 1, 1]);
      Object.assign(saved.customers[0], {
        home: { property_id: "WRONG-ROOT" },
        selected_retrofits: ["heat_pump"],
      });
      await mount();
      expect(
        within(screen.getByRole("combobox", { name: "Property" })).getAllByRole(
          "option",
        ),
      ).toHaveLength(count);
      expect(
        screen.getByRole("spinbutton", {
          name: "Property active-plan budget (£)",
        }),
      ).toHaveProperty("value", "5000");
      expect(api.assess).not.toHaveBeenCalledWith(
        expect.objectContaining({ property_id: "WRONG-ROOT" }),
        expect.anything(),
        expect.anything(),
      );
      fireEvent.change(screen.getByRole("combobox", { name: "Customer" }), {
        target: { value: "customer-2" },
      });
      expect(screen.getByRole("combobox", { name: "Property" })).toHaveProperty(
        "value",
        "customer-2-property-1",
      );
      expect(
        within(screen.getByRole("combobox", { name: "Property" })).getAllByRole(
          "option",
        ),
      ).toHaveLength(1);
      expect(api.whatIf).not.toHaveBeenCalled();
    },
  );
  it("persists only the selected property's active budget/deferrals and both versions; retains sibling memory", async () => {
    const sibling = structuredClone(saved.customers[0].properties[0]);
    const view = await mount();
    propertySelect(2);
    budget("7000");
    fireEvent.click(
      screen.getByRole("checkbox", { name: "Defer Air-source heat pump" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Save property changes" }),
    );
    await screen.findByText("Property changes saved.");
    expect(api.saveProperty).toHaveBeenCalledWith(
      "customer-1",
      "customer-1-property-2",
      expect.objectContaining({
        customer_version: 1,
        version: 1,
        preferences: expect.objectContaining({
          budget_gbp: 7000,
          deferred_retrofits: ["heat_pump"],
        }),
        home: expect.objectContaining({
          property_id: "HOME-customer-1-2",
          budget_gbp: 7000,
          excluded_retrofits: ["heat_pump"],
        }),
      }),
      expect.any(AbortSignal),
    );
    expect(saved.customers[0].properties[0]).toEqual(sibling);
    expect(api.saveCustomer).not.toHaveBeenCalled();
    view.unmount();
    await mount();
    propertySelect(2);
    expect(
      screen.getByRole("spinbutton", {
        name: "Property active-plan budget (£)",
      }),
    ).toHaveProperty("value", "7000");
    expect(
      screen.getByRole("checkbox", { name: "Defer Air-source heat pump" }),
    ).toHaveProperty("checked", true);
    propertySelect(1);
    expect(
      screen.getByRole("checkbox", { name: "Defer Air-source heat pump" }),
    ).toHaveProperty("checked", false);
  });
  it("protects both property drafts and customer settings on switches and unload", async () => {
    await mount();
    budget("4000");
    vi.mocked(window.confirm).mockReturnValue(false);
    propertySelect(2);
    expect(screen.getByRole("combobox", { name: "Property" })).toHaveProperty(
      "value",
      "customer-1-property-1",
    );
    expect(
      screen.getByRole("spinbutton", {
        name: "Property active-plan budget (£)",
      }),
    ).toHaveProperty("value", "4000");
    fireEvent.change(
      screen.getByRole("spinbutton", { name: "Shared portfolio budget (£)" }),
      { target: { value: "20000" } },
    );
    fireEvent.change(screen.getByRole("combobox", { name: "Customer" }), {
      target: { value: "customer-2" },
    });
    expect(screen.getByRole("combobox", { name: "Customer" })).toHaveProperty(
      "value",
      "customer-1",
    );
    const before = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(before);
    expect(before.defaultPrevented).toBe(true);
    vi.mocked(window.confirm).mockReturnValue(true);
    propertySelect(2);
    expect(
      screen.getByRole("spinbutton", { name: "Shared portfolio budget (£)" }),
    ).toHaveProperty("value", "");
    expect(
      screen.getByRole("spinbutton", {
        name: "Property active-plan budget (£)",
      }),
    ).toHaveProperty("value", "10000");
  });
  it("keeps a failed save and failed reload draft intact; no optimistic sibling mutation or silent retry", async () => {
    vi.mocked(api.saveProperty).mockRejectedValue(
      new ApiError(
        "Sibling save changed the customer version.",
        409,
        "stale_version",
      ),
    );
    const snapshot = structuredClone(saved);
    await mount();
    budget("4444");
    fireEvent.click(
      screen.getByRole("button", { name: "Save property changes" }),
    );
    await screen.findByText("Sibling save changed the customer version.");
    expect(
      screen.getByRole("spinbutton", {
        name: "Property active-plan budget (£)",
      }),
    ).toHaveProperty("value", "4444");
    expect(saved).toEqual(snapshot);
    expect(api.workspace).toHaveBeenCalledTimes(1);
    vi.mocked(api.workspace).mockRejectedValueOnce(
      new Error("Reload failed safely"),
    );
    fireEvent.click(
      screen.getAllByRole("button", { name: "Reload saved workspace" })[0],
    );
    await screen.findByText("Reload failed safely");
    expect(
      screen.getByRole("spinbutton", {
        name: "Property active-plan budget (£)",
      }),
    ).toHaveProperty("value", "4444");
    expect(api.saveProperty).toHaveBeenCalledOnce();
    vi.mocked(window.confirm).mockReturnValue(false);
    propertySelect(2);
    expect(screen.getByRole("combobox", { name: "Property" })).toHaveProperty(
      "value",
      "customer-1-property-1",
    );
  });
  it("adds only an explicitly confirmed fictional template, not another customer; max eight per owner", async () => {
    saved = multiWorkspace([7, 1, 1, 1]);
    await mount();
    const add = screen.getByRole("button", { name: "Add fictional property" });
    expect(add).toHaveProperty("disabled", true);
    fireEvent.change(
      screen.getByRole("combobox", { name: "Fictional property template" }),
      { target: { value: "DEMO-02" } },
    );
    expect(add).toHaveProperty("disabled", true);
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /new property is a fictional template helper/,
      }),
    );
    fireEvent.click(add);
    await screen.findByText(/Fictional property added/);
    expect(api.addProperty).toHaveBeenCalledWith(
      "customer-1",
      { customer_version: 1, template_id: "DEMO-02" },
      expect.any(AbortSignal),
    );
    expect(saved.customers).toHaveLength(4);
    expect(screen.getByRole("combobox", { name: "Property" })).toHaveProperty(
      "value",
      "customer-1-property-8",
    );
    expect(screen.getByText(/Eight-property limit reached/)).toBeTruthy();
    expect(
      screen.getByRole("spinbutton", {
        name: "Property active-plan budget (£)",
      }),
    ).toHaveProperty("value", "");
    expect(saved.customers[0].properties[7].events).toEqual([]);
    expect(
      screen
        .getByRole("combobox", { name: "Fictional property template" })
        .closest("fieldset"),
    ).toHaveProperty("disabled", true);
  });
  it("does not lose a property draft when an attempted add fails", async () => {
    vi.mocked(api.addProperty).mockRejectedValue(
      new ApiError("Add failed", 409, "stale_version"),
    );
    await mount();
    budget("4100");
    fireEvent.change(
      screen.getByRole("combobox", { name: "Fictional property template" }),
      { target: { value: "DEMO-01" } },
    );
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /new property is a fictional template helper/,
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Add fictional property" }),
    );
    await screen.findByText("Add failed");
    expect(
      screen.getByRole("spinbutton", {
        name: "Property active-plan budget (£)",
      }),
    ).toHaveProperty("value", "4100");
    expect(saved.customers[0].properties).toHaveLength(2);
  });
  it("completes only the target home, preserves siblings and customer reservations, then restores history", async () => {
    const sibling = structuredClone(saved.customers[0].properties[1]);
    const view = await mount();
    fireEvent.change(
      screen.getByRole("combobox", { name: "Completed improvement" }),
      { target: { value: "loft_insulation" } },
    );
    fireEvent.change(screen.getByLabelText("Completion date"), {
      target: { value: "2026-10-10" },
    });
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /I confirm this work is completed/,
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm completed work" }),
    );
    await screen.findByText(/Completed work saved/);
    expect(api.completeProperty).toHaveBeenCalledWith(
      "customer-1",
      "customer-1-property-1",
      expect.objectContaining({
        version: 1,
        customer_version: 1,
        kind: "completed",
        retrofit_id: "loft_insulation",
        confirmed: true,
      }),
      expect.any(AbortSignal),
    );
    expect(api.completeRetrofit).not.toHaveBeenCalled();
    expect(saved.customers[0].properties[1]).toEqual(sibling);
    expect(
      screen.getByRole("button", { name: "Update post-completion readings" }),
    ).toBeTruthy();
    expect(screen.getByText(/Planning cost reservation: £1,600/)).toBeTruthy();
    propertySelect(2);
    expect(
      screen.queryByRole("button", { name: "Update post-completion readings" }),
    ).toBeNull();
    expect(screen.getByText("No completed work recorded.")).toBeTruthy();
    propertySelect(1);
    nav("My home");
    expect(screen.getByText(/not independently verified/)).toHaveProperty(
      "textContent",
      expect.stringContaining("2026-10-10"),
    );
    view.unmount();
    window.history.replaceState(null, "", "#workspace");
    await mount();
    expect(screen.getByText(/Planning cost reservation: £1,600/)).toBeTruthy();
    expect(saved.customers[0].budget_summary.total_reserved_gbp).toBe(1600);
  });
});

describe("customer-wide settings, independent budgets and asynchronous boundaries", () => {
  it("saves customer preferences separately, inherits exclusions without changing raw property budgets", async () => {
    await mount();
    fireEvent.change(
      screen.getByRole("spinbutton", { name: "Shared portfolio budget (£)" }),
      { target: { value: "25000" } },
    );
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Exclude Solar panels for all properties",
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Save customer settings" }),
    );
    await screen.findByText(/Customer settings saved/);
    expect(api.saveCustomerSettings).toHaveBeenCalledWith(
      "customer-1",
      expect.objectContaining({
        version: 1,
        portfolio_budget_gbp: 25000,
        confirm_legacy_reserve: false,
        customer_preferences: expect.objectContaining({
          deferred_retrofits: ["solar_pv"],
        }),
      }),
      expect.any(AbortSignal),
    );
    expect(
      screen.getByRole("button", { name: "Save customer settings" }),
    ).toHaveProperty("disabled", true);
    expect(
      saved.customers[0].properties.map((p) => p.preferences.budget_gbp),
    ).toEqual([5000, 10000]);
    await waitFor(() =>
      expect(api.assess).toHaveBeenCalledWith(
        expect.objectContaining({
          budget_gbp: 5000,
          excluded_retrofits: ["solar_pv"],
        }),
        ["loft_insulation"],
        expect.any(AbortSignal),
      ),
    );
    budget("6000");
    fireEvent.click(
      screen.getByRole("button", { name: "Save property changes" }),
    );
    await screen.findByText("Property changes saved.");
    expect(api.saveProperty).toHaveBeenCalledWith(
      "customer-1",
      "customer-1-property-1",
      expect.objectContaining({
        customer_version: 2,
        version: 1,
        home: expect.objectContaining({ excluded_retrofits: [] }),
        preferences: expect.objectContaining({
          deferred_retrofits: [],
          budget_gbp: 6000,
        }),
      }),
      expect.any(AbortSignal),
    );
  });
  it("retains customer settings draft after exclusion conflict without deleting selected plans", async () => {
    vi.mocked(api.saveCustomerSettings).mockRejectedValue(
      new ApiError("Saved plan exclusion conflict", 409, "excluded_plan"),
    );
    await mount();
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Exclude Loft insulation for all properties",
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Save customer settings" }),
    );
    await screen.findByText("Saved plan exclusion conflict");
    expect(
      screen.getByRole("checkbox", {
        name: "Exclude Loft insulation for all properties",
      }),
    ).toHaveProperty("checked", true);
    expect(saved.customers[0].properties[0].selected_retrofits).toEqual([
      "loft_insulation",
    ]);
    expect(api.saveProperty).not.toHaveBeenCalled();
  });
  it("requires explicit legacy reserve confirmation (including zero) before setting a finite shared cap", async () => {
    saved.customers[0].legacy_completed_reserve_gbp = null;
    saved.customers[0].budget_summary = {
      planned_upper_gbp: 1600,
      completed_reserved_gbp: null,
      total_reserved_gbp: null,
      remaining_gbp: null,
      status: "needs_cost_evidence",
    };
    await mount();
    expect(
      screen.getByText(/Historical completion costs are unknown/),
    ).toBeTruthy();
    fireEvent.change(
      screen.getByRole("spinbutton", { name: "Shared portfolio budget (£)" }),
      { target: { value: "12000" } },
    );
    expect(
      screen.getByRole("button", { name: "Save customer settings" }),
    ).toHaveProperty("disabled", true);
    fireEvent.change(
      screen.getByRole("spinbutton", {
        name: "Aggregate legacy planning reserve (£)",
      }),
      { target: { value: "0" } },
    );
    expect(
      screen.getByRole("button", { name: "Save customer settings" }),
    ).toHaveProperty("disabled", true);
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /explicitly confirm this aggregate legacy/,
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Save customer settings" }),
    );
    await screen.findByText(/Customer settings saved/);
    expect(api.saveCustomerSettings).toHaveBeenCalledWith(
      "customer-1",
      expect.objectContaining({
        legacy_completed_reserve_gbp: 0,
        confirm_legacy_reserve: true,
      }),
      expect.any(AbortSignal),
    );
  });
  it("ignores late calculations/questions from another property even when display labels match", async () => {
    const late = deferred<Reply>();
    vi.mocked(api.whatIf).mockReturnValue(late.promise);
    await mount();
    nav("What if");
    await screen.findByRole("button", { name: /Send question/ });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Send question/ }),
      ).toHaveProperty("disabled", true),
    );
    fireEvent.change(screen.getByRole("textbox", { name: "Your question" }), {
      target: { value: "Explain this plan" },
    });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Send question/ }),
      ).toHaveProperty("disabled", false),
    );
    fireEvent.click(screen.getByRole("button", { name: /Send question/ }));
    const oldSignal = vi.mocked(api.whatIf).mock.calls[0][4];
    fireEvent.change(screen.getByRole("combobox", { name: "Customer" }), {
      target: { value: "customer-2" },
    });
    expect(oldSignal?.aborted).toBe(true);
    await act(async () =>
      late.resolve({
        status: "ok",
        message: "STALE OWNER ANSWER",
        lines: ["STALE OWNER ANSWER"],
        claim_ids: [],
        selected_retrofits: ["heat_pump"],
        assessment,
        applied: true,
        needs_clarification: false,
        parser_mode: "local",
        explanation_mode: "fallback",
      }),
    );
    expect(screen.queryByText("STALE OWNER ANSWER")).toBeNull();
    expect(saved.customers[1].properties[0].selected_retrofits).toEqual([
      "loft_insulation",
    ]);
    await waitFor(() =>
      expect(
        screen.getByRole("textbox", { name: "Your question" }),
      ).toHaveProperty("value", ""),
    );
  });
  it("prevents duplicate saves and aborts outstanding mutation on unmount", async () => {
    const late = deferred<CanonicalWorkspace>();
    vi.mocked(api.saveProperty).mockReturnValue(late.promise);
    const view = await mount();
    budget("4000");
    const button = screen.getByRole("button", {
      name: "Save property changes",
    });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(api.saveProperty).toHaveBeenCalledOnce();
    expect(screen.getByRole("combobox", { name: "Property" })).toHaveProperty(
      "disabled",
      true,
    );
    const signal = vi.mocked(api.saveProperty).mock.calls[0][3];
    view.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => late.resolve(saved));
  });
  it("prints owner/property identifiers and distinguishes active-plan budget from reserved completed costs", async () => {
    await mount();
    nav("My plan");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Print or save plan/ }),
      ).toHaveProperty("disabled", false),
    );
    expect(
      screen.getByText(
        /Customer ID: customer-1. Property ID: customer-1-property-1/,
      ),
    ).toBeTruthy();
    expect(screen.getByText("Property active-plan budget")).toBeTruthy();
    expect(screen.getByText(/not cumulative historical spending/)).toBeTruthy();
    expect(screen.getByText("Completed planning reservations")).toBeTruthy();
    expect(
      screen.getByText(/completion never makes that money available again/),
    ).toBeTruthy();
  });
});
