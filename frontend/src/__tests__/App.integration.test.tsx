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
import type { Home, RetrofitId } from "../types";
import {
  assessment,
  catalogue,
  deferred,
  health,
  home,
  reply,
} from "./fixtures";

const otherHome: Home = {
  ...home,
  property_id: "UNIT-FLAT",
  property_type: "Flat",
  roof_access: false,
  floor_area_m2: 65,
};

function resultFor(input: Home, ids: RetrofitId[] | null) {
  return {
    ...assessment,
    home: input,
    selected_retrofits: ids || [],
    recommendations: assessment.recommendations.map((item) => ({
      ...item,
      feasible:
        input.property_id === otherHome.property_id
          ? item.id !== "loft_insulation"
          : true,
    })),
  };
}

beforeEach(() => {
  window.history.replaceState(null, "", "#dashboard");
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.spyOn(api, "homes").mockResolvedValue([home, otherHome]);
  vi.spyOn(api, "catalogue").mockResolvedValue(catalogue);
  vi.spyOn(api, "health").mockResolvedValue(health);
  vi.spyOn(api, "assess").mockImplementation(async (input, selected) =>
    resultFor(input, selected),
  );
  vi.spyOn(api, "metrics").mockResolvedValue({
    status: "unavailable",
    metrics: null,
  });
  vi.spyOn(api, "whatIf").mockResolvedValue(reply);
});

async function mounted() {
  const view = render(<App />);
  await screen.findByRole("heading", { name: /A considered plan/ });
  return view;
}

function navigate(label: string) {
  fireEvent.click(
    within(
      screen.getByRole("navigation", { name: "Main navigation" }),
    ).getByRole("link", { name: label }),
  );
}

describe("lead composition integration — no App/CSS edits", () => {
  it("uses actual returned demo labels and never starts a Gemini request on load", async () => {
    await mounted();
    const select = screen.getByRole("combobox", { name: "Choose a home" });
    expect(
      within(select).getByRole("option", { name: "UNIT-TEST · Semi detached" }),
    ).toBeTruthy();
    expect(
      within(select).getByRole("option", { name: "UNIT-FLAT · Flat" }),
    ).toBeTruthy();
    expect(select).toHaveProperty("value", home.property_id);
    expect(api.whatIf).not.toHaveBeenCalled();
  });

  it("switches homes and resets the selected package", async () => {
    await mounted();
    fireEvent.click(screen.getByText("Add improvements"));
    fireEvent.click(
      screen.getByRole("checkbox", { name: /Air-source heat pump/ }),
    );
    await waitFor(() =>
      expect(api.assess).toHaveBeenCalledWith(
        home,
        ["heat_pump"],
        expect.any(AbortSignal),
      ),
    );
    fireEvent.change(screen.getByRole("combobox", { name: "Choose a home" }), {
      target: { value: otherHome.property_id },
    });
    await waitFor(() =>
      expect(api.assess).toHaveBeenCalledWith(
        otherHome,
        [],
        expect.any(AbortSignal),
      ),
    );
    expect(
      screen.getByRole("combobox", { name: "Choose a home" }),
    ).toHaveProperty("value", otherHome.property_id);
    expect(screen.queryByText("1 improvement selected")).toBeNull();
  });

  it("opens the user-entered home form with unknown readings", async () => {
    await mounted();
    fireEvent.change(screen.getByRole("combobox", { name: "Choose a home" }), {
      target: { value: "MY-HOME" },
    });
    await screen.findByRole("heading", {
      name: "A little detail makes a better plan",
    });
    expect(
      screen.getByRole("heading", { name: "1. Home basics" }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Continue to energy" }));
    expect(
      screen.getByRole("spinbutton", { name: /Annual grid electricity/ }),
    ).toHaveProperty("value", "");
    expect(
      screen.getByRole("spinbutton", { name: /Annual gas consumption/ }),
    ).toHaveProperty("value", "");
    // The full editor retains the original all-at-once path and truth boundary.
    fireEvent.click(screen.getByRole("button", { name: "Use full editor" }));
    expect(
      screen.getByRole("checkbox", { name: /fictional scenario/ }),
    ).toHaveProperty("checked", false);
  });

  it("keeps an API-rejected package explicit and removes old scenario output", async () => {
    await mounted();
    vi.mocked(api.assess).mockImplementation(async (input, ids) => {
      if (ids?.includes("heat_pump"))
        throw new ApiError(
          "Combined package exceeds the budget",
          422,
          "invalid_scenario",
        );
      return resultFor(input, ids);
    });
    fireEvent.click(screen.getByText("Add improvements"));
    fireEvent.click(
      screen.getByRole("checkbox", { name: /Air-source heat pump/ }),
    );
    const error = await screen.findByRole("alert");
    expect(error.textContent).toContain("Combined package exceeds the budget");
    expect(
      screen.queryByRole("table", {
        name: "Annual purchased energy · kWh/year",
      }),
    ).toBeNull();
    expect(screen.getByRole("button", { name: "Retry package" })).toBeTruthy();
  });

  it("does not retain an answer after manually changing the package", async () => {
    await mounted();
    navigate("What if");
    fireEvent.change(screen.getByRole("textbox", { name: "Your question" }), {
      target: { value: "Explain my score" },
    });
    vi.mocked(api.whatIf).mockResolvedValue({
      ...reply,
      selected_retrofits: [],
      assessment: resultFor(home, []),
    });
    fireEvent.click(screen.getByRole("button", { name: /Send question/ }));
    await screen.findByText(reply.lines[0]);
    fireEvent.click(screen.getByText("Add improvements"));
    fireEvent.click(screen.getByRole("checkbox", { name: /Loft insulation/ }));
    expect(screen.queryByText(reply.lines[0])).toBeNull();
  });

  it("aborts a what-if request when navigating away", async () => {
    const pending = deferred<typeof reply>();
    vi.mocked(api.whatIf).mockReturnValue(pending.promise);
    await mounted();
    navigate("What if");
    fireEvent.change(screen.getByRole("textbox", { name: "Your question" }), {
      target: { value: "Add loft insulation" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Send question/ }));
    const signal = vi.mocked(api.whatIf).mock.calls[0][4];
    navigate("Dashboard");
    expect(signal?.aborted).toBe(true);
    await act(async () =>
      pending.resolve({
        ...reply,
        applied: true,
        selected_retrofits: ["loft_insulation"],
      }),
    );
    expect(screen.queryByText("1 improvement selected")).toBeNull();
  });

  it("renders reports without a stale scenario export after a rejected package", async () => {
    await mounted();
    vi.mocked(api.assess).mockRejectedValue(
      new ApiError("Invalid package", 422, "invalid_scenario"),
    );
    fireEvent.click(screen.getByText("Add improvements"));
    fireEvent.click(
      screen.getByRole("checkbox", { name: /Air-source heat pump/ }),
    );
    await screen.findByRole("alert");
    navigate("Reports");
    expect(
      screen.getByRole("button", { name: /^Download JSON$/ }),
    ).toHaveProperty("disabled", true);
  });

  it("renders the home form with no duplicate-key warnings", async () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    await mounted();
    navigate("My home");
    expect(
      screen.getByRole("button", { name: /Save home & reset plan/ }),
    ).toBeTruthy();
    const keyWarnings = errors.mock.calls.filter((call) =>
      call.some(
        (value) =>
          typeof value === "string" && /unique.*key|same key/i.test(value),
      ),
    );
    expect(keyWarnings).toEqual([]);
  });

  it("shows a recoverable connection state instead of empty or invented results", async () => {
    vi.mocked(api.homes).mockRejectedValue(
      new ApiError("API unavailable", 0, "connection"),
    );
    render(<App />);
    expect(
      await screen.findByRole("heading", { name: "Let’s reconnect your home" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Retry connection" }),
    ).toBeTruthy();
    expect(screen.queryByText("37")).toBeNull();
  });
});
