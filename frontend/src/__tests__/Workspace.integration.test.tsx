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
import { assessment, catalogue, deferred, health } from "./fixtures";
import { workspace as fixture } from "./workspaceFixtures";
import type { Workspace, LegacyWorkspace } from "../types";

let saved: LegacyWorkspace;
beforeEach(() => {
  saved = structuredClone(fixture);
  window.history.replaceState(null, "", "#dashboard");
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.spyOn(api, "homes").mockResolvedValue(
    fixture.customers.map((c) => c.home),
  );
  vi.spyOn(api, "catalogue").mockResolvedValue(catalogue);
  vi.spyOn(api, "health").mockResolvedValue(health);
  vi.spyOn(api, "workspace").mockImplementation(async () =>
    structuredClone(saved),
  );
  vi.spyOn(api, "createWorkspace").mockImplementation(async () =>
    structuredClone(saved),
  );
  vi.spyOn(api, "deleteWorkspace").mockResolvedValue({ deleted: true });
  vi.spyOn(api, "completeRetrofit").mockImplementation(async () =>
    structuredClone(saved),
  );
  vi.spyOn(api, "saveCustomer").mockImplementation(async (id, update) => {
    saved = {
      ...saved,
      customers: saved.customers.map((c) =>
        c.id === id
          ? {
              ...c,
              ...update,
              version: c.version + 1,
              baseline_status: update.baseline_confirmed_after_completion
                ? "current"
                : c.baseline_status,
            }
          : c,
      ),
    };
    return structuredClone(saved);
  });
  vi.spyOn(api, "assess").mockImplementation(async (home, selected) => ({
    ...assessment,
    home,
    selected_retrofits: selected || [],
    recommendations: assessment.recommendations.map((r) => ({
      ...r,
      feasible: !home.excluded_retrofits?.includes(r.id),
    })),
    scenario: {
      ...assessment.scenario,
      electricity_saving_kwh:
        home.electricity_kwh === null
          ? null
          : assessment.scenario.electricity_saving_kwh,
      gas_saving_kwh:
        home.gas_kwh === null ? null : assessment.scenario.gas_saving_kwh,
    },
  }));
});
async function mount() {
  const view = render(<App />);
  await screen.findByRole("heading", { name: /A considered plan/ });
  await waitFor(() =>
    expect(
      screen.queryByRole("combobox", { name: "Customer" }) ??
        screen.getByRole("combobox", { name: "Choose a home" }),
    ).toHaveProperty("disabled", false),
  );
  return view;
}
function nav(name: string) {
  fireEvent.click(
    within(
      screen.getByRole("navigation", { name: "Main navigation" }),
    ).getByRole("link", { name }),
  );
}
function changeBudget(value: string) {
  fireEvent.change(
    screen.getByRole("spinbutton", { name: "Property active-plan budget (£)" }),
    { target: { value } },
  );
}

describe("private fictional workspace journey", () => {
  it("keeps saved workspace management available when calculation bootstrap fails", async () => {
    vi.mocked(api.homes).mockRejectedValue(
      new ApiError("Demo service unavailable", 503, "unavailable"),
    );
    window.history.replaceState(null, "", "#workspace");
    render(<App />);
    expect(
      await screen.findByRole("button", {
        name: "Export saved workspace JSON",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Delete all saved workspace data" }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("heading", { name: "Let’s reconnect your home" }),
    ).toBeNull();
  });
  it("restores saved household preferences and selection without creating or explaining", async () => {
    saved.customers[0].preferences.budget_gbp = 5000;
    saved.customers[0].preferences.deferred_retrofits = ["solar_pv"];
    await mount();
    expect(api.createWorkspace).not.toHaveBeenCalled();
    expect(screen.getByRole("combobox", { name: "Customer" })).toHaveProperty(
      "value",
      "customer-1",
    );
    expect(api.assess).toHaveBeenCalledWith(
      expect.objectContaining({
        budget_gbp: 5000,
        excluded_retrofits: ["solar_pv"],
      }),
      ["loft_insulation"],
      expect.any(AbortSignal),
    );
    expect(screen.getByText("1 improvement selected")).toBeTruthy();
  });
  it("requires explicit opt-in and never copies temporary own-home inputs", async () => {
    vi.mocked(api.workspace).mockRejectedValue(
      new ApiError("Missing workspace", 401, "workspace_required"),
    );
    await mount();
    nav("Saved workspace");
    const create = screen.getByRole("button", {
      name: "Create my fictional workspace",
    });
    expect(create).toHaveProperty("disabled", true);
    expect(api.createWorkspace).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("checkbox", { name: /I agree to save fictional/ }),
    );
    fireEvent.click(create);
    await screen.findByText(/Fictional workspace created/);
    expect(api.createWorkspace).toHaveBeenCalledWith(expect.any(AbortSignal));
    expect(api.saveCustomer).not.toHaveBeenCalled();
  });
  it("applies deferrals to calculations immediately and persists all required versioned fields", async () => {
    await mount();
    nav("Saved workspace");
    changeBudget("5000");
    fireEvent.click(
      screen.getByRole("checkbox", { name: "Defer Loft insulation" }),
    );
    fireEvent.change(screen.getByRole("combobox", { name: "Review status" }), {
      target: { value: "reviewing" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: /What matters/ }), {
      target: { value: "carbon" },
    });
    await waitFor(() =>
      expect(api.assess).toHaveBeenCalledWith(
        expect.objectContaining({
          budget_gbp: 5000,
          excluded_retrofits: ["loft_insulation"],
        }),
        [],
        expect.any(AbortSignal),
      ),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Save property changes" }),
    );
    await screen.findByText("Property changes saved.");
    expect(api.saveCustomer).toHaveBeenCalledWith(
      "customer-1",
      expect.objectContaining({
        version: 1,
        home: expect.objectContaining({
          budget_gbp: 5000,
          excluded_retrofits: ["loft_insulation"],
        }),
        preferences: {
          budget_gbp: 5000,
          deferred_retrofits: ["loft_insulation"],
          priority: "carbon",
          disruption: "flexible",
        },
        selected_retrofits: [],
        review_status: "reviewing",
      }),
      expect.any(AbortSignal),
    );
  });
  it("restores saved changes after a new application mount", async () => {
    const view = await mount();
    nav("Saved workspace");
    changeBudget("4250");
    fireEvent.click(
      screen.getByRole("button", { name: "Save property changes" }),
    );
    await screen.findByText("Property changes saved.");
    view.unmount();
    window.history.replaceState(null, "", "#dashboard");
    await mount();
    nav("Saved workspace");
    expect(
      screen.getByRole("spinbutton", {
        name: "Property active-plan budget (£)",
      }),
    ).toHaveProperty("value", "4250");
    expect(api.createWorkspace).not.toHaveBeenCalled();
  });
  it("protects unsaved household changes on home switch and before unload", async () => {
    await mount();
    nav("Saved workspace");
    changeBudget("4100");
    vi.mocked(window.confirm).mockReturnValue(false);
    fireEvent.change(screen.getByRole("combobox", { name: "Customer" }), {
      target: { value: "customer-2" },
    });
    expect(
      screen.getByRole("spinbutton", {
        name: "Property active-plan budget (£)",
      }),
    ).toHaveProperty("value", "4100");
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(api.saveCustomer).not.toHaveBeenCalled();
  });
  it("handles stale versions without overwriting drafts and requires confirmed reload", async () => {
    vi.mocked(api.saveCustomer).mockRejectedValue(
      new ApiError("Another tab changed this household.", 409, "stale_version"),
    );
    await mount();
    nav("Saved workspace");
    changeBudget("4000");
    fireEvent.click(
      screen.getByRole("button", { name: "Save property changes" }),
    );
    await screen.findByRole("alert");
    expect(
      screen.getByRole("spinbutton", {
        name: "Property active-plan budget (£)",
      }),
    ).toHaveProperty("value", "4000");
    expect(
      screen.getByRole("button", { name: "Save property changes" }),
    ).toHaveProperty("disabled", true);
    vi.mocked(window.confirm).mockReturnValue(false);
    fireEvent.click(
      screen.getAllByRole("button", { name: "Reload saved workspace" })[0],
    );
    expect(api.workspace).toHaveBeenCalledTimes(1);
    vi.mocked(window.confirm).mockReturnValue(true);
    fireEvent.click(
      screen.getAllByRole("button", { name: "Reload saved workspace" })[0],
    );
    await waitFor(() =>
      expect(
        screen.getByRole("spinbutton", {
          name: "Property active-plan budget (£)",
        }),
      ).toHaveProperty("value", ""),
    );
  });
  it("requires completion confirmation and consumes invalidated baseline and history from the response", async () => {
    vi.mocked(api.completeRetrofit).mockImplementation(async () => {
      saved.customers[0] = {
        ...saved.customers[0],
        version: 2,
        selected_retrofits: [],
        baseline_status: "needs_update",
        home: {
          ...saved.customers[0].home,
          insulation: "good",
          electricity_kwh: null,
          gas_kwh: null,
        },
        events: [
          {
            id: "event-1",
            kind: "completed",
            retrofit_id: "loft_insulation",
            completed_on: "2026-10-10",
            created_at: "2026-10-10T13:00:00Z",
          },
        ],
      };
      return structuredClone(saved);
    });
    await mount();
    nav("Saved workspace");
    fireEvent.change(
      screen.getByRole("combobox", { name: "Completed improvement" }),
      { target: { value: "loft_insulation" } },
    );
    fireEvent.change(screen.getByLabelText("Completion date"), {
      target: { value: "2026-10-10" },
    });
    expect(
      screen.getByRole("button", { name: "Confirm completed work" }),
    ).toHaveProperty("disabled", true);
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /I confirm this work is completed/,
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm completed work" }),
    );
    await screen.findByText(/Completed work saved/);
    expect(api.completeRetrofit).toHaveBeenCalledWith(
      "customer-1",
      {
        version: 1,
        kind: "completed",
        retrofit_id: "loft_insulation",
        completed_on: "2026-10-10",
        confirmed: true,
      },
      expect.any(AbortSignal),
    );
    expect(
      screen.getByRole("button", { name: "Update post-completion readings" }),
    ).toBeTruthy();
    expect(screen.getByRole("list")).toHaveProperty(
      "textContent",
      expect.stringContaining("Loft insulation"),
    );
    nav("My home");
    expect(
      screen.getByRole("spinbutton", { name: /Annual gas consumption/ }),
    ).toHaveProperty("value", "");
    expect(
      screen.getByRole("checkbox", { name: /describe the home after/ }),
    ).toHaveProperty("checked", false);
  });
  it("rejects a future completion date in the UI", async () => {
    await mount();
    nav("Saved workspace");
    fireEvent.change(
      screen.getByRole("combobox", { name: "Completed improvement" }),
      { target: { value: "loft_insulation" } },
    );
    fireEvent.change(screen.getByLabelText("Completion date"), {
      target: { value: "2999-01-01" },
    });
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /I confirm this work is completed/,
      }),
    );
    expect(
      screen.getByRole("button", { name: "Confirm completed work" }),
    ).toHaveProperty("disabled", true);
    expect(api.completeRetrofit).not.toHaveBeenCalled();
  });
  it("sends the visible post-completion reading confirmation only after the user checks it", async () => {
    saved.customers[0].baseline_status = "needs_update";
    saved.customers[0].home.electricity_kwh = null;
    saved.customers[0].home.gas_kwh = null;
    saved.customers[0].selected_retrofits = [];
    await mount();
    nav("My home");
    fireEvent.change(
      screen.getByRole("spinbutton", { name: /Annual grid electricity/ }),
      { target: { value: "3200" } },
    );
    fireEvent.change(
      screen.getByRole("spinbutton", { name: /Annual gas consumption/ }),
      { target: { value: "9000" } },
    );
    const confirmation = screen.getByRole("checkbox", {
      name: /describe the home after/,
    });
    expect(confirmation).toHaveProperty("required", true);
    fireEvent.click(confirmation);
    fireEvent.click(
      screen.getByRole("button", { name: "Apply home edits & reset plan" }),
    );
    await screen.findByRole("heading", { name: /A considered plan/ });
    nav("Saved workspace");
    fireEvent.click(
      screen.getByRole("button", { name: "Save property changes" }),
    );
    await screen.findByText("Property changes saved.");
    expect(api.saveCustomer).toHaveBeenCalledWith(
      "customer-1",
      expect.objectContaining({
        baseline_confirmed_after_completion: true,
        home: expect.objectContaining({
          electricity_kwh: 3200,
          gas_kwh: 9000,
          data_kind: "synthetic_demo",
        }),
      }),
      expect.any(AbortSignal),
    );
  });
  it("deletes only after confirmation and never implicitly recreates the workspace", async () => {
    await mount();
    nav("Saved workspace");
    const button = screen.getByRole("button", {
      name: "Delete all saved workspace data",
    });
    expect(button).toHaveProperty("disabled", true);
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: /all saved workspace records will be deleted/,
      }),
    );
    fireEvent.click(button);
    await screen.findByRole("button", {
      name: "Create my fictional workspace",
    });
    expect(api.deleteWorkspace).toHaveBeenCalledOnce();
    expect(api.createWorkspace).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Create my fictional workspace" }),
    ).toHaveProperty("disabled", true);
  });
  it("keeps own-home screening ephemeral even when a saved workspace exists", async () => {
    await mount();
    fireEvent.change(screen.getByRole("combobox", { name: "Customer" }), {
      target: { value: "MY-HOME" },
    });
    nav("Saved workspace");
    expect(
      screen.queryByRole("button", { name: "Save property changes" }),
    ).toBeNull();
    expect(
      screen.getByText(/It cannot be saved in this workspace/),
    ).toBeTruthy();
    expect(api.saveCustomer).not.toHaveBeenCalled();
  });
  it("prevents duplicate saves and ignores a late save after unmount", async () => {
    const late = deferred<Workspace>();
    vi.mocked(api.saveCustomer).mockReturnValue(late.promise);
    const view = await mount();
    nav("Saved workspace");
    changeBudget("500");
    const save = screen.getByRole("button", { name: "Save property changes" });
    fireEvent.click(save);
    fireEvent.click(save);
    expect(api.saveCustomer).toHaveBeenCalledOnce();
    const signal = vi.mocked(api.saveCustomer).mock.calls[0][2];
    view.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => late.resolve(saved));
  });
});

describe("recovery and native navigation", () => {
  it("preserves modified link clicks for opening another tab", async () => {
    await mount();
    const link = within(
      screen.getByRole("navigation", { name: "Main navigation" }),
    ).getByRole("link", { name: "Homes" });
    const click = new MouseEvent("click", {
      bubbles: true,
      cancelable: true,
      ctrlKey: true,
      button: 0,
    });
    let preventedByApp: boolean | undefined;
    // jsdom does not implement native modifier/new-tab behaviour. Observe React's
    // decision, then suppress only jsdom's unsupported default navigation.
    document.addEventListener(
      "click",
      (event) => {
        preventedByApp = event.defaultPrevented;
        event.preventDefault();
      },
      { once: true },
    );
    link.dispatchEvent(click);
    expect(preventedByApp).toBe(false);
    expect(window.location.hash).toBe("#dashboard");
  });
  it("protects form edits on route and back navigation", async () => {
    await mount();
    nav("My home");
    fireEvent.change(screen.getByRole("spinbutton", { name: /Floor area/ }), {
      target: { value: "117" },
    });
    vi.mocked(window.confirm).mockReturnValue(false);
    nav("Dashboard");
    expect(
      screen.getByRole("spinbutton", { name: /Floor area/ }),
    ).toHaveProperty("value", "117");
    act(() => {
      window.history.replaceState(null, "", "#dashboard");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(window.location.hash).toBe("#home");
    expect(
      screen.getByRole("spinbutton", { name: /Floor area/ }),
    ).toHaveProperty("value", "117");
  });
  it("offers undo after clearing the selected plan", async () => {
    await mount();
    fireEvent.click(
      screen.getByRole("button", { name: "Clear selected improvements" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Undo clear" }));
    expect(screen.getByText("1 improvement selected")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Undo clear" })).toBeNull();
  });
});
