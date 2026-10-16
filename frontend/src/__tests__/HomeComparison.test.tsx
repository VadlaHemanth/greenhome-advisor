import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HomeComparison, HomeThumbnail } from "../HomeComparison";
import { home } from "./fixtures";
import { RETROFIT_IDS, type Home, type Recommendation } from "../types";

const recommendations: Recommendation[] = RETROFIT_IDS.map((id) => ({
  id,
  name: id,
  feasible: true,
  suitability: "Medium",
  reason: "Test only",
  cost_gbp: [0, 0],
  standalone: null,
}));
const props = { home, selected: [], recommendations, loading: false };
let reduced = false;
let motionListener: ((e: { matches: boolean }) => void) | undefined;
const removeMotionListener = vi.fn();
class TestPointerEvent extends MouseEvent {
  pointerId: number;
  isPrimary: boolean;
  pointerType: string;
  constructor(type: string, init: PointerEventInit = {}) {
    super(type, init);
    this.pointerId = init.pointerId ?? 1;
    this.isPrimary = init.isPrimary ?? true;
    this.pointerType = init.pointerType ?? "touch";
  }
}
beforeEach(() => {
  reduced = false;
  motionListener = undefined;
  vi.stubGlobal("PointerEvent", TestPointerEvent);
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: reduced,
      addEventListener: (_: string, cb: typeof motionListener) => {
        motionListener = cb;
      },
      removeEventListener: removeMotionListener,
    })),
  );
});
const scene = (name: "Current" | "Proposed") =>
  screen.getByRole("img", { name: new RegExp(`^${name} home`) });
const geometry = (name: "Current" | "Proposed") =>
  Array.from(scene(name).querySelectorAll("[data-face]"))
    .map((p) => p.getAttribute("points"))
    .join("|");

describe("HomeComparison", () => {
  it("shows two labelled, identical no-op views and a permanent text legend", () => {
    render(<HomeComparison {...props} />);
    expect(geometry("Current")).toBe(geometry("Proposed"));
    expect(screen.getByText(/No proposed changes/)).toBeTruthy();
    expect(
      screen.getByRole("group", { name: "Feature status legend" }),
    ).toBeTruthy();
    expect(screen.getByText(/not a survey/i)).toBeTruthy();
  });
  it("links both cameras for named buttons, keyboard zoom/rotation and reset", () => {
    render(<HomeComparison {...props} />);
    const initial = geometry("Current");
    fireEvent.click(screen.getByRole("button", { name: "Rotate right" }));
    expect(geometry("Current")).not.toBe(initial);
    expect(geometry("Current")).toBe(geometry("Proposed"));
    fireEvent.click(screen.getByRole("button", { name: "Reset view" }));
    expect(geometry("Current")).toBe(initial);
    const viewport = screen.getByRole("group", { name: "Current home camera" });
    fireEvent.keyDown(viewport, { key: "ArrowLeft" });
    expect(geometry("Current")).not.toBe(initial);
    fireEvent.keyDown(viewport, { key: "Home" });
    expect(geometry("Current")).toBe(initial);
    fireEvent.keyDown(viewport, { key: "+" });
    expect(geometry("Current")).not.toBe(initial);
    fireEvent.keyDown(viewport, { key: "Home" });
    fireEvent.click(screen.getByRole("button", { name: "Zoom out" }));
    expect(geometry("Current")).not.toBe(initial);
    expect(fetch).not.toHaveBeenCalled();
  });
  it("provides current/proposed/compare controls without removing the change list", () => {
    render(<HomeComparison {...props} selected={["solar_pv"]} />);
    fireEvent.click(screen.getByRole("button", { name: "Show proposed home" }));
    expect(
      screen
        .getByRole("button", { name: "Show proposed home" })
        .getAttribute("aria-pressed"),
    ).toBe("true");
    expect(
      screen.getByRole("region", {
        name: "Recorded features and proposed changes",
      }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Compare both homes" }));
    expect(scene("Current")).toBeTruthy();
    expect(scene("Proposed")).toBeTruthy();
  });
  it("focuses and highlights all five features with status annotations", () => {
    render(<HomeComparison {...props} selected={[...RETROFIT_IDS]} />);
    for (const name of [
      "Roof insulation",
      "Window panes",
      "Heat pump fan",
      "Solar panels",
      "Smart controls",
    ]) {
      const button = screen.getByRole("button", {
        name: `Focus ${name.toLowerCase()}`,
      });
      fireEvent.click(button);
      expect(button.getAttribute("aria-pressed")).toBe("true");
      expect(
        screen.getByRole("status", { name: "Feature detail" }).textContent,
      ).toContain(name);
    }
    expect(screen.getByText(/not an internal location/i)).toBeTruthy();
    expect(document.querySelector('[data-highlighted="true"]')).toBeTruthy();
  });
  it("suppresses pending proposals and updates immediately on clear or a new home", () => {
    const view = render(<HomeComparison {...props} selected={["heat_pump"]} />);
    expect(
      scene("Proposed").querySelector('[data-feature="heat_pump"]'),
    ).not.toBeNull();
    view.rerender(
      <HomeComparison {...props} selected={["heat_pump"]} loading />,
    );
    expect(
      scene("Proposed").querySelector('[data-feature="heat_pump"]'),
    ).toBeNull();
    expect(screen.getByText(/Checking selected improvements/)).toBeTruthy();
    view.rerender(<HomeComparison {...props} />);
    expect(geometry("Current")).toBe(geometry("Proposed"));
    const missing = {
      ...home,
      property_id: "NEW",
      property_type: null,
      heating: null,
      glazing: null,
      insulation: null,
      solar_kwp: null,
      smart_controls: null,
    };
    view.rerender(
      <HomeComparison
        {...props}
        home={missing}
        selected={["heat_pump"]}
        recommendations={[]}
        loading
      />,
    );
    expect(screen.getByText("Property type unknown")).toBeTruthy();
    expect(document.querySelector('[data-feature="heat_pump"]')).toBeNull();
    expect(screen.getAllByText("Unknown").length).toBeGreaterThanOrEqual(5);
  });
  it("explains unavailable and unassessed selections without proposed geometry", () => {
    render(
      <HomeComparison
        {...props}
        selected={["solar_pv", "heat_pump"]}
        recommendations={[
          {
            ...recommendations.find((r) => r.id === "solar_pv")!,
            feasible: false,
            reason: "Roof permission is missing.",
          },
        ]}
      />,
    );
    expect(screen.getByText(/Roof permission is missing/)).toBeTruthy();
    expect(screen.getByText(/Awaiting current recommendation/)).toBeTruthy();
    expect(geometry("Current")).toBe(geometry("Proposed"));
  });
  it("resets camera and focus immediately for changed anonymous home inputs", () => {
    const view = render(
      <HomeComparison {...props} home={{ ...home, property_id: null }} />,
    );
    const initial = geometry("Current");
    fireEvent.click(screen.getByRole("button", { name: "Focus window panes" }));
    fireEvent.click(screen.getByRole("button", { name: "Rotate left" }));
    expect(geometry("Current")).not.toBe(initial);
    view.rerender(
      <HomeComparison
        {...props}
        home={{ ...home, property_id: null, gas_kwh: 8000 }}
      />,
    );
    expect(geometry("Current")).toBe(initial);
    expect(
      screen
        .getByRole("button", { name: "Focus window panes" })
        .getAttribute("aria-pressed"),
    ).toBe("false");
  });
  it("rotates only horizontal pointer drags and does not prevent vertical scrolling", () => {
    render(<HomeComparison {...props} />);
    const viewport = screen.getByRole("group", { name: "Current home camera" });
    const capture = vi.fn();
    const release = vi.fn();
    Object.assign(viewport, {
      setPointerCapture: capture,
      releasePointerCapture: release,
      hasPointerCapture: () => true,
    });
    const initial = geometry("Current");
    fireEvent.pointerDown(viewport, { clientX: 30, clientY: 30, button: 0 });
    fireEvent.pointerMove(viewport, { clientX: 33, clientY: 95 });
    expect(geometry("Current")).toBe(initial);
    expect(capture).not.toHaveBeenCalled();
    fireEvent.pointerUp(viewport);
    fireEvent.pointerDown(viewport, { clientX: 30, clientY: 30, button: 0 });
    fireEvent.pointerMove(viewport, { clientX: 95, clientY: 33 });
    expect(geometry("Current")).not.toBe(initial);
    expect(geometry("Current")).toBe(geometry("Proposed"));
    expect(capture).toHaveBeenCalledWith(1);
    fireEvent.pointerCancel(viewport);
    expect(release).toHaveBeenCalledWith(1);
  });
  it("does no idle animation, bounds user-triggered fan motion and cleans up on hidden/unmount", () => {
    vi.useFakeTimers();
    const raf = vi.fn();
    vi.stubGlobal("requestAnimationFrame", raf);
    const view = render(<HomeComparison {...props} selected={["heat_pump"]} />);
    expect(vi.getTimerCount()).toBe(0);
    expect(raf).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Focus heat pump fan" }),
    );
    expect(document.querySelector('[data-animating="true"]')).toBeTruthy();
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(document.querySelector('[data-animating="true"]')).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
    fireEvent.click(
      screen.getByRole("button", { name: "Focus heat pump fan" }),
    );
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: true,
    });
    fireEvent(document, new Event("visibilitychange"));
    expect(document.querySelector('[data-animating="true"]')).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: false,
    });
    fireEvent(document, new Event("visibilitychange"));
    fireEvent.click(
      screen.getByRole("button", { name: "Focus heat pump fan" }),
    );
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
    expect(removeMotionListener).toHaveBeenCalled();
  });
  it("respects reduced motion at mount and when the preference changes", () => {
    vi.useFakeTimers();
    reduced = true;
    render(<HomeComparison {...props} selected={["heat_pump"]} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Focus heat pump fan" }),
    );
    expect(document.querySelector('[data-animating="true"]')).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
    act(() => {
      motionListener?.({ matches: false });
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Focus heat pump fan" }),
    );
    expect(document.querySelector('[data-animating="true"]')).toBeTruthy();
    act(() => {
      motionListener?.({ matches: true });
    });
    expect(document.querySelector('[data-animating="true"]')).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });
  it("cancels motion when offscreen, does not restart on re-entry and disconnects its observer", () => {
    vi.useFakeTimers();
    let observeVisibility: (
      entries: { isIntersecting: boolean }[],
    ) => void = () => {};
    const disconnect = vi.fn(),
      observe = vi.fn();
    class Observer {
      constructor(callback: typeof observeVisibility) {
        observeVisibility = callback;
      }
      observe = observe;
      disconnect = disconnect;
    }
    vi.stubGlobal("IntersectionObserver", Observer);
    const view = render(<HomeComparison {...props} selected={["heat_pump"]} />);
    expect(observe).toHaveBeenCalledOnce();
    fireEvent.click(
      screen.getByRole("button", { name: "Focus heat pump fan" }),
    );
    expect(vi.getTimerCount()).toBe(1);
    act(() => {
      observeVisibility([{ isIntersecting: false }]);
    });
    expect(vi.getTimerCount()).toBe(0);
    expect(document.querySelector('[data-animating="true"]')).toBeNull();
    act(() => {
      observeVisibility([{ isIntersecting: true }]);
    });
    expect(vi.getTimerCount()).toBe(0);
    view.unmount();
    expect(disconnect).toHaveBeenCalledOnce();
  });
  it("animates a new confirmed selection briefly, but cancels immediately when cleared or loading", () => {
    vi.useFakeTimers();
    const view = render(<HomeComparison {...props} />);
    view.rerender(<HomeComparison {...props} selected={["heat_pump"]} />);
    expect(document.querySelector('[data-animating="true"]')).toBeTruthy();
    view.rerender(
      <HomeComparison {...props} selected={["heat_pump"]} loading />,
    );
    expect(document.querySelector('[data-animating="true"]')).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
    expect(geometry("Current")).toBe(geometry("Proposed"));
    view.rerender(<HomeComparison {...props} />);
    expect(vi.getTimerCount()).toBe(0);
  });
  it("does not change the camera for up/down keys or secondary pointers, and ends cancelled drags", () => {
    render(<HomeComparison {...props} />);
    const viewport = screen.getByRole("group", { name: "Current home camera" });
    const initial = geometry("Current");
    fireEvent.keyDown(viewport, { key: "ArrowDown" });
    fireEvent.keyDown(viewport, { key: "ArrowUp" });
    fireEvent.keyDown(viewport, { key: "ArrowLeft", ctrlKey: true });
    fireEvent.pointerDown(viewport, { button: 2 });
    fireEvent.pointerMove(viewport, { clientX: 500, clientY: 0 });
    expect(geometry("Current")).toBe(initial);
    fireEvent.pointerDown(viewport, {
      button: 0,
      isPrimary: false,
      clientX: 0,
      clientY: 0,
    });
    fireEvent.pointerMove(viewport, {
      clientX: 500,
      clientY: 0,
      isPrimary: false,
    });
    expect(geometry("Current")).toBe(initial);
    fireEvent.pointerDown(viewport, { button: 0, clientX: 0, clientY: 0 });
    fireEvent.pointerMove(viewport, { clientX: 40, clientY: 0 });
    const rotated = geometry("Current");
    expect(rotated).not.toBe(initial);
    fireEvent.pointerCancel(viewport);
    fireEvent.pointerMove(viewport, { clientX: 100, clientY: 0 });
    expect(geometry("Current")).toBe(rotated);
  });
});

describe("HomeThumbnail", () => {
  it.each([
    "Detached",
    "Semi detached",
    "Mid terrace",
    "End terrace",
    "Bungalow",
    "Flat",
    null,
  ] as const)(
    "renders %s as static labelled SVG, without camera hooks, controls or effects",
    (property_type: Home["property_type"]) => {
      vi.useFakeTimers();
      const view = render(<HomeThumbnail home={{ ...home, property_type }} />);
      expect(within(view.container).getByRole("img")).toBeTruthy();
      expect(view.container.querySelector("polygon")).toBeTruthy();
      expect(view.container.querySelector("button,[tabindex]")).toBeNull();
      expect(matchMedia).not.toHaveBeenCalled();
      expect(vi.getTimerCount()).toBe(0);
      expect(fetch).not.toHaveBeenCalled();
    },
  );
});
