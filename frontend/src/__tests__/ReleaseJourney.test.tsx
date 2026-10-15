import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Welcome } from "../Welcome";
import { HomeSchematic } from "../HomeSchematic";
import { AdviserSummary } from "../AdviserSummary";
import { home } from "./fixtures";

describe("public release journey", () => {
  it("makes example and temporary own-home choices explicit", () => {
    const demo = vi.fn(),
      own = vi.fn(),
      evidence = vi.fn();
    render(<Welcome onExample={demo} onOwnHome={own} onEvidence={evidence} />);
    fireEvent.click(
      screen.getByRole("button", { name: /Explore an example home/i }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /Assess my own home/i }),
    );
    expect(demo).toHaveBeenCalledOnce();
    expect(own).toHaveBeenCalledOnce();
    expect(screen.getByText(/England and Wales/)).toBeTruthy();
    expect(screen.getByText(/temporary/i)).toBeTruthy();
  });
  it("labels the house as schematic and distinguishes proposed from installed", () => {
    const { rerender } = render(
      <HomeSchematic home={home} selected={["solar_pv", "heat_pump"]} />,
    );
    expect(
      screen.getByRole("img", { name: /Home improvement schematic/ }),
    ).toBeTruthy();
    expect(screen.getByText("Solar panels · proposed")).toBeTruthy();
    expect(screen.getByText("Heat pump · proposed")).toBeTruthy();
    rerender(<HomeSchematic home={{ ...home, solar_kwp: 3 }} selected={[]} />);
    expect(screen.getByText("Solar panels · installed")).toBeTruthy();
    expect(screen.queryByText("Heat pump · proposed")).toBeNull();
  });
  it("does not render an unavailable adviser aggregate as zero", () => {
    render(<AdviserSummary rows={[]} loading={false} />);
    expect(screen.getByText("Not assessed")).toBeTruthy();
    expect(screen.queryByText("0 kg")).toBeNull();
  });
});
