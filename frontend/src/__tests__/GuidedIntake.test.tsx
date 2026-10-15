import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HomeForm } from "../HomeForm";
import { api } from "../api";
import { assessment, deferred, home } from "./fixtures";
import { monthlyCsv, monthlyPreview } from "./energyFixtures";

const blankHome = {
  ...home,
  property_id: "MY-HOME",
  property_type: null,
  electricity_kwh: null,
  gas_kwh: null,
  epc_rating: null,
  floor_area_m2: null,
  roof_access: null,
  heating: null,
  data_kind: "user_entered" as const,
};

function next() {
  fireEvent.click(screen.getByRole("button", { name: /Continue to/ }));
}
function csvFields() {
  fireEvent.click(screen.getByText("Use monthly CSV instead (optional)"));
  fireEvent.change(
    screen.getByLabelText("Last month in your 12-month period"),
    { target: { value: "2025-12" } },
  );
  fireEvent.change(
    screen.getByRole("textbox", { name: "Monthly energy CSV" }),
    { target: { value: monthlyCsv } },
  );
}

describe("guided intake", () => {
  it("has three short sections and review; blanks are not guessed and saving is explicit", async () => {
    const assess = vi.spyOn(api, "assess").mockResolvedValue(assessment);
    const save = vi.fn();
    render(<HomeForm home={blankHome} initialMode="guided" onSave={save} />);
    expect(
      screen.getByRole("heading", { name: "1. Home basics" }),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Save home/ })).toBeNull();
    expect(
      screen
        .getByRole("combobox", { name: "Recorded EPC rating" })
        .getAttribute("aria-describedby"),
    ).toBe("help-epc_rating");
    next();
    expect(screen.getByRole("heading", { name: "2. Energy" })).toBeTruthy();
    next();
    expect(
      screen.getByRole("heading", { name: "3. Features & permissions" }),
    ).toBeTruthy();
    next();
    expect(screen.getByRole("heading", { name: "4. Review" })).toBeTruthy();
    expect(assess).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: /Save home & reset plan/ }),
    );
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0]).toMatchObject({
      property_type: null,
      electricity_kwh: null,
      gas_kwh: null,
      epc_rating: null,
      roof_access: null,
      floor_area_m2: null,
      data_kind: "user_entered",
    });
  });

  it("retains draft data across Back and the full editor toggle", async () => {
    render(<HomeForm home={blankHome} initialMode="guided" onSave={vi.fn()} />);
    fireEvent.change(screen.getByRole("spinbutton", { name: /Floor area/ }), {
      target: { value: "87" },
    });
    next();
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByRole("heading", { name: "2. Energy" }),
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(
      screen.getByRole("spinbutton", { name: /Floor area/ }),
    ).toHaveProperty("value", "87");
    fireEvent.click(screen.getByRole("button", { name: "Use full editor" }));
    expect(
      screen.getByRole("spinbutton", { name: /Annual gas consumption/ }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Use guided intake" }));
    expect(
      screen.getByRole("spinbutton", { name: /Floor area/ }),
    ).toHaveProperty("value", "87");
  });

  it("requires explicit confirmation for zero gas; heating never sets zero", async () => {
    render(<HomeForm home={blankHome} initialMode="guided" onSave={vi.fn()} />);
    next();
    fireEvent.change(
      screen.getByRole("spinbutton", { name: /Annual gas consumption/ }),
      { target: { value: "0" } },
    );
    next();
    expect(screen.getByRole("alert").textContent).toContain("Confirm no gas");
    fireEvent.click(screen.getByRole("checkbox", { name: /I confirm no gas/ }));
    next();
    fireEvent.change(
      screen.getByRole("combobox", { name: "Main heating system" }),
      { target: { value: "heat_pump" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    fireEvent.click(screen.getByRole("checkbox", { name: /I confirm no gas/ }));
    expect(
      screen.getByRole("spinbutton", { name: /Annual gas consumption/ }),
    ).toHaveProperty("value", "");
  });

  it("previews monthly coverage/table without mutating annuals, then applies exact totals", async () => {
    const monthly = vi
      .spyOn(api, "energyInputs")
      .mockResolvedValue(monthlyPreview);
    render(<HomeForm home={blankHome} initialMode="guided" onSave={vi.fn()} />);
    next();
    csvFields();
    expect(monthly).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Preview 12-month totals" }),
    );
    const preview = await screen.findByRole("region", {
      name: "Monthly energy preview",
    });
    expect(within(preview).getByRole("table").textContent).toContain("2025-01");
    expect(within(preview).getByRole("status").textContent).toContain(
      "Electricity: 12/12",
    );
    expect(
      screen.getByRole("spinbutton", { name: /Annual grid electricity/ }),
    ).toHaveProperty("value", "");
    fireEvent.click(
      screen.getByRole("button", { name: "Apply these annual totals" }),
    );
    expect(
      screen.getByRole("spinbutton", { name: /Annual grid electricity/ }),
    ).toHaveProperty("value", "2640");
    expect(
      screen.getByRole("spinbutton", { name: /Annual gas consumption/ }),
    ).toHaveProperty("value", "9600");
    expect(monthly).toHaveBeenCalledWith(
      monthlyCsv,
      "2025-12",
      expect.any(AbortSignal),
    );
  });

  it("applies partial fuel as unknown and resets the post-completion confirmation", async () => {
    vi.spyOn(api, "energyInputs").mockResolvedValue({
      ...monthlyPreview,
      status: "partial",
      gas_kwh: null,
      purchased_kwh: null,
      coverage: { electricity_months: 12, gas_months: 11 },
      months: monthlyPreview.months.map((row, i) =>
        i === 0 ? { ...row, gas_kwh: null } : row,
      ),
    });
    render(
      <HomeForm
        home={home}
        workspaceBaseline="needs_update"
        onSave={vi.fn()}
      />,
    );
    const confirmed = screen.getByRole("checkbox", {
      name: /describe the home after/,
    });
    fireEvent.click(confirmed);
    csvFields();
    fireEvent.click(
      screen.getByRole("button", { name: "Preview 12-month totals" }),
    );
    await screen.findByRole("region", { name: "Monthly energy preview" });
    fireEvent.click(
      screen.getByRole("button", { name: "Apply these annual totals" }),
    );
    expect(
      screen.getByRole("spinbutton", { name: /Annual gas consumption/ }),
    ).toHaveProperty("value", "");
    expect(confirmed).toHaveProperty("checked", false);
    expect(confirmed).toHaveProperty("disabled", true);
  });

  it("even complete monthly data does not self-confirm a post-work baseline", async () => {
    vi.spyOn(api, "energyInputs").mockResolvedValue(monthlyPreview);
    const save = vi.fn();
    const assess = vi.spyOn(api, "assess").mockResolvedValue(assessment);
    render(
      <HomeForm home={home} workspaceBaseline="needs_update" onSave={save} />,
    );
    csvFields();
    fireEvent.click(
      screen.getByRole("button", { name: "Preview 12-month totals" }),
    );
    await screen.findByRole("region", { name: "Monthly energy preview" });
    fireEvent.click(
      screen.getByRole("button", { name: "Apply these annual totals" }),
    );
    fireEvent.click(screen.getByRole("button", { name: /Apply home edits/ }));
    expect(save).not.toHaveBeenCalled();
    expect(assess).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("checkbox", { name: /describe the home after/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: /Apply home edits/ }));
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith(
        expect.objectContaining({
          electricity_kwh: 2640,
          gas_kwh: 9600,
          data_kind: "synthetic_demo",
        }),
        true,
      ),
    );
  });

  it("invalidates an in-flight preview when the month changes and ignores a late result", async () => {
    const pending = deferred<typeof monthlyPreview>();
    const monthly = vi
      .spyOn(api, "energyInputs")
      .mockReturnValue(pending.promise);
    render(<HomeForm home={home} onSave={vi.fn()} />);
    csvFields();
    fireEvent.click(
      screen.getByRole("button", { name: "Preview 12-month totals" }),
    );
    fireEvent.change(
      screen.getByLabelText("Last month in your 12-month period"),
      { target: { value: "2025-11" } },
    );
    expect(monthly.mock.calls[0][2]?.aborted).toBe(true);
    await act(async () => pending.resolve(monthlyPreview));
    expect(
      screen.queryByRole("button", { name: "Apply these annual totals" }),
    ).toBeNull();
  });

  it("keeps CSV edits in the unsaved-change guard and clears them on a different home", () => {
    const dirty = vi.fn();
    const props = { onSave: vi.fn(), onDirtyChange: dirty };
    const { rerender } = render(<HomeForm home={home} {...props} />);
    csvFields();
    expect(dirty).toHaveBeenLastCalledWith(true);
    rerender(<HomeForm home={blankHome} {...props} />);
    expect(dirty).toHaveBeenLastCalledWith(false);
    fireEvent.click(screen.getByText("Use monthly CSV instead (optional)"));
    expect(
      screen.getByRole("textbox", { name: "Monthly energy CSV" }),
    ).toHaveProperty("value", "");
  });
});
