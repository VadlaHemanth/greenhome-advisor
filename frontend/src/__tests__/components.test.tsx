import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  Asset,
  FuelTable,
  Modal,
  RetrofitPicker,
  ScoreGauge,
} from "../components";
import { isNumber, moneyRange, newHome, number } from "../format";
import { Dashboard } from "../Dashboard";
import { assessment, home } from "./fixtures";

describe("numeric display never invents missing values", () => {
  it.each([null, undefined, NaN, Infinity, "123", false])(
    "renders %s as unavailable",
    (value) => {
      expect(number(value)).toBe("Unavailable");
      expect(isNumber(value)).toBe(false);
    },
  );
  it("keeps zero and negative savings", () => {
    expect(number(0)).toBe("0");
    expect(number(-2720, 0, true)).toBe("-2,720");
    expect(number(9600, 0, true)).toBe("+9,600");
    expect(moneyRange([null, 500])).toBe("Unavailable");
  });
  it("starts a custom home with unknown readings and permissions", () => {
    expect(newHome()).toMatchObject({
      data_kind: "user_entered",
      gas_kwh: null,
      electricity_kwh: null,
      roof_access: null,
      heat_pump_ready: null,
    });
  });
});

describe("evidence-backed components", () => {
  it("shows the signed fuel changes supplied by the engine", () => {
    render(<FuelTable assessment={assessment} />);
    expect(screen.getByText("-2,720")).toBeTruthy();
    expect(screen.getByText("+9,600")).toBeTruthy();
    expect(screen.getByText(/Negative values mean an increase/)).toBeTruthy();
  });
  it("does not turn missing current gas into a zero", () => {
    render(
      <FuelTable
        assessment={{
          ...assessment,
          baseline: { ...assessment.baseline, gas_kwh: null },
        }}
      />,
    );
    expect(screen.getByRole("row", { name: /Gas/ }).textContent).toContain(
      "Unavailable",
    );
  });
  it("does not draw an available score when the score is missing", () => {
    render(
      <ScoreGauge
        assessment={{
          ...assessment,
          score: {
            ...assessment.score,
            total: null,
            classification: "Unavailable",
          },
        }}
      />,
    );
    expect(screen.getByText("Missing inputs")).toBeTruthy();
    expect(screen.queryByText("37")).toBeNull();
  });
  it("prevents adding infeasible items but lets the user remove an old invalid selection", () => {
    const change = vi.fn();
    const recommendations = assessment.recommendations.map((r) => ({
      ...r,
      feasible: false,
    }));
    render(
      <RetrofitPicker
        label="Package"
        recommendations={recommendations}
        selected={["heat_pump"]}
        onChange={change}
      />,
    );
    expect(
      screen.getByRole("checkbox", { name: /Loft insulation/ }),
    ).toHaveProperty("disabled", true);
    fireEvent.click(
      screen.getByRole("checkbox", { name: /Air-source heat pump/ }),
    );
    expect(change).toHaveBeenCalledWith([]);
  });
  it("provides readable fallback when an asset cannot load", () => {
    render(<Asset src="/assets/missing.webp" alt="A conceptual house" />);
    fireEvent.error(screen.getByRole("img", { name: "A conceptual house" }));
    expect(screen.getByText("Concept image unavailable")).toBeTruthy();
  });
  it("never displays a synthetic value range for actual home inputs", () => {
    const withValue = {
      ...assessment,
      value_impact: {
        status: "synthetic_illustration",
        low_gbp: 1234,
        high_gbp: 5678,
        low_percent: 1,
        high_percent: 2,
        note: "Synthetic test fixture.",
      },
    };
    render(
      <Dashboard
        home={{ ...home, data_kind: "user_entered" }}
        baseline={assessment}
        plan={withValue}
        planLoading={false}
        edit={vi.fn()}
        navigate={vi.fn()}
        showScore={vi.fn()}
        showDetails={vi.fn()}
      />,
    );
    expect(screen.getByText("No market estimate")).toBeTruthy();
    expect(screen.queryByText("£1,234–£5,678")).toBeNull();
  });
});

describe("native modal wiring", () => {
  it("opens a labelled native dialog, routes Escape, and restores trigger focus", () => {
    // jsdom has no native top-layer dialog implementation. This checks component
    // wiring only; actual focus trapping belongs to the lead's browser audit.
    const show = vi.fn(function (this: HTMLDialogElement) {
      this.open = true;
    });
    const closeNative = vi.fn(function (this: HTMLDialogElement) {
      this.open = false;
    });
    Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
      configurable: true,
      value: show,
    });
    Object.defineProperty(HTMLDialogElement.prototype, "close", {
      configurable: true,
      value: closeNative,
    });
    const trigger = document.createElement("button");
    trigger.textContent = "Open score";
    document.body.append(trigger);
    trigger.focus();
    const close = vi.fn();
    const { unmount } = render(
      <Modal title="Score details" close={close}>
        <p>Score content</p>
      </Modal>,
    );
    expect(show).toHaveBeenCalledOnce();
    const dialog = screen.getByRole("dialog", { name: "Score details" });
    fireEvent(
      dialog,
      new Event("cancel", { bubbles: false, cancelable: true }),
    );
    expect(close).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Close dialog" }));
    expect(close).toHaveBeenCalledTimes(2);
    unmount();
    expect(closeNative).toHaveBeenCalledOnce();
    expect(document.activeElement).toBe(trigger);
    trigger.remove();
    Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
    Reflect.deleteProperty(HTMLDialogElement.prototype, "close");
  });
});
