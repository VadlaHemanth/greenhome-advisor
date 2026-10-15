import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HomeForm } from "../HomeForm";
import { api, ApiError } from "../api";
import { assessment, deferred, home } from "./fixtures";

function submitForm() {
  fireEvent.click(
    screen.getByRole("button", { name: /Save home & reset plan/ }),
  );
}

describe("home form truth boundary", () => {
  it("uses the verified NEED construction-period definitions", () => {
    render(<HomeForm home={home} onSave={vi.fn()} />);
    const input = screen.getByRole("combobox", {
      name: "When was it built?",
    }) as HTMLSelectElement;
    expect(
      Array.from(input.options).map((option) => [
        option.value,
        option.textContent,
      ]),
    ).toEqual([
      ["", "Unknown"],
      ["1", "Before 1930"],
      ["2", "1930–1972"],
      ["3", "1973–1999"],
      ["4", "2000 or later"],
    ]);
    expect(input.value).toBe("2");
  });
  it("saves an edited demonstration as user_entered by default", async () => {
    const save = vi.fn();
    const assess = vi.spyOn(api, "assess").mockResolvedValue(assessment);
    render(<HomeForm home={home} onSave={save} />);
    fireEvent.change(screen.getByRole("spinbutton", { name: /Floor area/ }), {
      target: { value: "110" },
    });
    submitForm();
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save.mock.calls[0][0]).toMatchObject({
      data_kind: "user_entered",
      floor_area_m2: 110,
    });
    expect(assess.mock.calls[0][1]).toEqual([]);
  });

  it("permits synthetic mode only through an explicit fictional choice", async () => {
    vi.spyOn(api, "assess").mockResolvedValue(assessment);
    const save = vi.fn();
    render(<HomeForm home={home} onSave={save} />);
    fireEvent.click(
      screen.getByRole("checkbox", { name: /fictional scenario/ }),
    );
    submitForm();
    await waitFor(() => expect(save).toHaveBeenCalled());
    expect(save.mock.calls[0][0].data_kind).toBe("synthetic_demo");
  });

  it("preserves missing fuel, missing permissions and explicit zero as different states", async () => {
    vi.spyOn(api, "assess").mockResolvedValue(assessment);
    const save = vi.fn();
    render(<HomeForm home={home} onSave={save} />);
    fireEvent.change(
      screen.getByRole("spinbutton", { name: /Annual gas consumption/ }),
      { target: { value: "" } },
    );
    fireEvent.change(
      screen.getByRole("spinbutton", { name: /Annual grid electricity/ }),
      { target: { value: "0" } },
    );
    fireEvent.change(screen.getByRole("combobox", { name: /Roof access/ }), {
      target: { value: "" },
    });
    submitForm();
    await waitFor(() => expect(save).toHaveBeenCalled());
    expect(save.mock.calls[0][0]).toMatchObject({
      gas_kwh: null,
      electricity_kwh: 0,
      roof_access: null,
    });
  });

  it("omits blank assumptions so the engine supplies disclosed defaults", async () => {
    vi.spyOn(api, "assess").mockResolvedValue(assessment);
    const save = vi.fn();
    render(<HomeForm home={home} onSave={save} />);
    fireEvent.click(screen.getByText("Review calculation assumptions"));
    fireEvent.change(
      screen.getByRole("spinbutton", { name: /Space-heating share/ }),
      { target: { value: "" } },
    );
    submitForm();
    await waitFor(() => expect(save).toHaveBeenCalled());
    expect(save.mock.calls[0][0]).not.toHaveProperty("space_heat_fraction");
  });

  it("does not save a server-rejected home", async () => {
    vi.spyOn(api, "assess").mockRejectedValue(
      new ApiError("Invalid home inputs", 422, "invalid_scenario"),
    );
    const save = vi.fn();
    render(<HomeForm home={home} onSave={save} />);
    submitForm();
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      expect.stringContaining("previous home remains unchanged"),
    );
    expect(save).not.toHaveBeenCalled();
  });

  it("cancels pending validation on editor unmount", async () => {
    const pending = deferred<typeof assessment>();
    const assess = vi.spyOn(api, "assess").mockReturnValue(pending.promise);
    const save = vi.fn();
    const { unmount } = render(<HomeForm home={home} onSave={save} />);
    submitForm();
    const signal = assess.mock.calls[0][2];
    unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      pending.resolve(assessment);
    });
    expect(save).not.toHaveBeenCalled();
  });

  it("resets inputs when a different home arrives without a parent remount", () => {
    const { rerender } = render(<HomeForm home={home} onSave={vi.fn()} />);
    fireEvent.change(screen.getByRole("spinbutton", { name: /Floor area/ }), {
      target: { value: "999" },
    });
    rerender(
      <HomeForm
        home={{ ...home, property_id: "OTHER-HOME", floor_area_m2: 65 }}
        onSave={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("spinbutton", { name: /Floor area/ }),
    ).toHaveProperty("value", "65");
    expect(
      screen.getByRole("checkbox", { name: /fictional scenario/ }),
    ).toHaveProperty("checked", false);
  });
  it("links allowlisted server field errors and focuses the invalid field", async () => {
    vi.spyOn(api, "assess").mockRejectedValue(
      new ApiError("Check home inputs", 422, "invalid_input", ["gas_kwh"]),
    );
    render(<HomeForm home={home} onSave={vi.fn()} />);
    submitForm();
    const field = screen.getByRole("spinbutton", {
      name: /Annual gas consumption/,
    });
    await waitFor(() => expect(document.activeElement).toBe(field));
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(field.getAttribute("aria-describedby")).toContain("error-gas_kwh");
  });
  it("requires confirmation for replacement fuels and resets confirmation if readings change", () => {
    render(
      <HomeForm
        home={home}
        workspaceBaseline="needs_update"
        onSave={vi.fn()}
      />,
    );
    const confirmation = screen.getByRole("checkbox", {
      name: /describe the home after/,
    });
    expect(confirmation).toHaveProperty("required", true);
    fireEvent.click(confirmation);
    expect(confirmation).toHaveProperty("checked", true);
    fireEvent.change(
      screen.getByRole("spinbutton", { name: /Annual gas consumption/ }),
      { target: { value: "" } },
    );
    expect(confirmation).toHaveProperty("checked", false);
    expect(confirmation).toHaveProperty("disabled", true);
  });
});
