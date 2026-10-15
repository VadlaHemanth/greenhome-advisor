import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HomeForm } from "../HomeForm";
import { api } from "../api";
import {
  latestCompletedOn,
  periodIncludesPreCompletion,
} from "../workspaceModel";
import { assessment, home } from "./fixtures";
import { monthlyCsv, monthlyPreview } from "./energyFixtures";
import { multiWorkspace } from "./multiPropertyFixtures";

async function applyCsv() {
  fireEvent.click(screen.getByText("Use monthly CSV instead (optional)"));
  fireEvent.change(
    screen.getByLabelText("Last month in your 12-month period"),
    { target: { value: "2025-12" } },
  );
  fireEvent.change(
    screen.getByRole("textbox", { name: "Monthly energy CSV" }),
    { target: { value: monthlyCsv } },
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Preview 12-month totals" }),
  );
  await screen.findByRole("region", { name: "Monthly energy preview" });
  fireEvent.click(
    screen.getByRole("button", { name: "Apply these annual totals" }),
  );
}

describe("property-specific post-completion CSV cutoff", () => {
  it("uses only the target property's latest occurrence date, not a sibling's event or created_at", () => {
    const [first, second] = multiWorkspace([2]).customers[0].properties;
    first.events = [
      {
        id: "a",
        kind: "completed",
        retrofit_id: "loft_insulation",
        completed_on: "2025-02-01",
        created_at: "2026-10-11T00:00:00Z",
      },
      {
        id: "b",
        kind: "completed",
        retrofit_id: "smart_controls",
        completed_on: "2025-04-20",
        created_at: "2026-10-10T00:00:00Z",
      },
    ];
    second.events = [
      {
        id: "c",
        kind: "completed",
        retrofit_id: "solar_pv",
        completed_on: "2024-12-31",
        created_at: "2026-10-11T00:00:00Z",
      },
    ];
    expect(latestCompletedOn(first)).toBe("2025-04-20");
    expect(latestCompletedOn(second)).toBe("2024-12-31");
    expect(
      periodIncludesPreCompletion("2025-01", latestCompletedOn(first)),
    ).toBe(true);
    expect(
      periodIncludesPreCompletion("2025-01", latestCompletedOn(second)),
    ).toBe(false);
    expect(
      periodIncludesPreCompletion("2025-04", latestCompletedOn(first)),
    ).toBe(true);
    expect(
      periodIncludesPreCompletion("2025-05", latestCompletedOn(first)),
    ).toBe(false);
    expect(latestCompletedOn(null)).toBeUndefined();
  });
  it("blocks a complete old period even if checkbox/submit are attempted; manual changes must replace both stale fuels", async () => {
    vi.spyOn(api, "energyInputs").mockResolvedValue(monthlyPreview);
    const assess = vi.spyOn(api, "assess").mockResolvedValue(assessment),
      save = vi.fn();
    render(
      <HomeForm
        home={home}
        workspaceBaseline="needs_update"
        baselineAfterDate="2025-04-20"
        onSave={save}
      />,
    );
    await applyCsv();
    const confirmation = screen.getByRole("checkbox", {
      name: /describe the home after/,
    });
    const submit = screen.getByRole("button", { name: /Apply home edits/ });
    expect(
      screen.getByText(
        /This period includes time before completed work; cannot confirm/,
      ),
    ).toBeTruthy();
    expect(confirmation).toHaveProperty("disabled", true);
    expect(submit).toHaveProperty("disabled", true);
    fireEvent.submit(screen.getByRole("form", { name: "Home intake" }));
    expect(save).not.toHaveBeenCalled();
    expect(assess).not.toHaveBeenCalled();
    fireEvent.change(
      screen.getByRole("spinbutton", { name: /Annual grid electricity/ }),
      { target: { value: "2700" } },
    );
    expect(confirmation).toHaveProperty("disabled", true);
    fireEvent.change(
      screen.getByRole("spinbutton", { name: /Annual gas consumption/ }),
      { target: { value: "9700" } },
    );
    expect(confirmation).toHaveProperty("disabled", false);
    expect(
      screen.getByText(
        /Manual readings and your post-work confirmation are not independently verified/,
      ),
    ).toBeTruthy();
    fireEvent.click(confirmation);
    fireEvent.click(submit);
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith(
        expect.objectContaining({ electricity_kwh: 2700, gas_kwh: 9700 }),
        true,
      ),
    );
  });
  it("allows a full period starting after the target's completion month, with explicit confirmation still required", async () => {
    vi.spyOn(api, "energyInputs").mockResolvedValue(monthlyPreview);
    const assess = vi.spyOn(api, "assess").mockResolvedValue(assessment),
      save = vi.fn();
    render(
      <HomeForm
        home={home}
        workspaceBaseline="needs_update"
        baselineAfterDate="2024-12-31"
        onSave={save}
      />,
    );
    await applyCsv();
    const confirmation = screen.getByRole("checkbox", {
      name: /describe the home after/,
    });
    expect(confirmation).toHaveProperty("disabled", false);
    fireEvent.click(screen.getByRole("button", { name: /Apply home edits/ }));
    expect(assess).not.toHaveBeenCalled();
    fireEvent.click(confirmation);
    fireEvent.click(screen.getByRole("button", { name: /Apply home edits/ }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
  });
  it("resets an old applied period when changing to the sibling home and its own cutoff", async () => {
    vi.spyOn(api, "energyInputs").mockResolvedValue(monthlyPreview);
    const { rerender } = render(
      <HomeForm
        home={home}
        workspaceBaseline="needs_update"
        baselineAfterDate="2025-04-20"
        onSave={vi.fn()}
      />,
    );
    await applyCsv();
    expect(
      screen.getByRole("checkbox", { name: /describe the home after/ }),
    ).toHaveProperty("disabled", true);
    rerender(
      <HomeForm
        home={{ ...home, property_id: "SIBLING" }}
        workspaceBaseline="needs_update"
        baselineAfterDate="2024-12-31"
        onSave={vi.fn()}
      />,
    );
    expect(
      screen.queryByText(
        /This period includes time before completed work; cannot confirm/,
      ),
    ).toBeNull();
    await applyCsv();
    expect(
      screen.getByRole("checkbox", { name: /describe the home after/ }),
    ).toHaveProperty("disabled", false);
  });
  it("does not let a refreshed current baseline or editor toggle bypass an applied old CSV period", async () => {
    vi.spyOn(api, "energyInputs").mockResolvedValue(monthlyPreview);
    render(
      <HomeForm
        home={home}
        workspaceBaseline="current"
        baselineAfterDate="2025-04-20"
        onSave={vi.fn()}
      />,
    );
    await applyCsv();
    fireEvent.click(screen.getByRole("button", { name: "Use guided intake" }));
    for (let step = 0; step < 3; step++)
      fireEvent.click(screen.getByRole("button", { name: /Continue to/ }));
    expect(
      screen.getByRole("button", { name: /Apply home edits/ }),
    ).toHaveProperty("disabled", true);
    expect(
      screen.getByRole("checkbox", { name: /describe the home after/ }),
    ).toHaveProperty("disabled", true);
  });
});
