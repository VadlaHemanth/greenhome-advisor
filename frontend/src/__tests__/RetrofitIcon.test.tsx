import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RetrofitIcon } from "../RetrofitIcon";
import { RecommendationCard } from "../components";
import { RETROFIT_IDS } from "../types";
import { assessment } from "./fixtures";
import iconStyles from "../retrofitIcons.css?raw";

describe("RetrofitIcon", () => {
  it.each(RETROFIT_IDS)("renders %s as decorative native SVG", (id) => {
    const { container } = render(
      <span>
        <RetrofitIcon id={id} />
        <span>Visible retrofit name</span>
      </span>,
    );
    const svg = container.querySelector("svg")!;
    expect(svg.namespaceURI).toBe("http://www.w3.org/2000/svg");
    expect(svg.getAttribute("viewBox")).toBe("0 0 64 64");
    expect(svg.getAttribute("data-retrofit")).toBe(id);
    expect(svg.getAttribute("aria-hidden")).toBe("true");
    expect(svg.getAttribute("focusable")).toBe("false");
    expect(svg.hasAttribute("tabindex")).toBe(false);
    expect(svg.hasAttribute("aria-label")).toBe(false);
    expect(svg.querySelector("title")).toBeNull();
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText("Visible retrofit name")).toBeTruthy();
  });

  it("uses distinct geometry for all five measures, not a shared house glyph", () => {
    const { container } = render(
      <>
        {RETROFIT_IDS.map((id) => (
          <RetrofitIcon key={id} id={id} />
        ))}
      </>,
    );
    const geometry = [...container.querySelectorAll("svg")].map((svg) =>
      [...svg.querySelectorAll("path, rect, circle")].map((shape) => ({
        tag: shape.tagName,
        geometry: ["d", "x", "y", "width", "height", "rx", "cx", "cy", "r"]
          .map((attribute) => shape.getAttribute(attribute))
          .join("|"),
      })),
    );
    expect(new Set(geometry.map((shapes) => JSON.stringify(shapes))).size).toBe(
      5,
    );
    expect(
      container.querySelector('[data-part="roof"]')?.getAttribute("d"),
    ).toContain("M7 29 32 10 57 29");
    expect(
      container.querySelectorAll('[data-part="insulation-layers"] path'),
    ).toHaveLength(4);
    const panes = container.querySelectorAll('[data-part="window-panes"] rect');
    expect(panes).toHaveLength(2);
    expect(panes[0].getAttribute("x")).not.toBe(panes[1].getAttribute("x"));
    expect(
      container
        .querySelector('[data-part="control-dial"] circle')
        ?.getAttribute("r"),
    ).toBe("13");
    expect(
      container
        .querySelector('[data-part="control-dial"] path')
        ?.getAttribute("d"),
    ).toContain("a9 9");
    expect(container.querySelectorAll('[data-part="fan"] path')).toHaveLength(
      3,
    );
    expect(container.querySelectorAll('[data-part="fan"] circle')).toHaveLength(
      2,
    );
    expect(
      container
        .querySelector('[data-retrofit="solar_pv"] > path:nth-child(2)')
        ?.getAttribute("d"),
    ).toBe("M17 20h34l7 26H8Z");
    expect(
      container.querySelector('[data-part="solar-grid"]')?.getAttribute("d"),
    ).toBe("m28 20-1 26M40 20l3 26M14 29h39M11 37h45");
  });

  it.each([
    ["sm", "32"],
    ["md", "48"],
    ["lg", "72"],
  ] as const)("supports the %s size and a caller class", (size, dimension) => {
    const { container } = render(
      <RetrofitIcon id="loft_insulation" size={size} className="parent-icon" />,
    );
    const svg = container.querySelector("svg")!;
    expect(svg.getAttribute("width")).toBe(dimension);
    expect(svg.getAttribute("height")).toBe(dimension);
    expect(svg.classList.contains("parent-icon")).toBe(true);
    expect(svg.classList.contains(`retrofit-icon--${size}`)).toBe(true);
  });

  it("needs no network, raster media, external SVG references, or CSS images", () => {
    const xhr = vi.spyOn(XMLHttpRequest.prototype, "open");
    const { container } = render(
      <>
        {RETROFIT_IDS.map((id) => (
          <RecommendationCard
            key={id}
            item={{ ...assessment.recommendations[0], id }}
            selected={false}
            onToggle={vi.fn()}
            onDetails={vi.fn()}
          />
        ))}
      </>,
    );
    expect(container.querySelectorAll("svg.retrofit-icon")).toHaveLength(5);
    expect(
      container.querySelector(
        "img, image, feImage, video, audio, source, iframe, object, embed, foreignObject, use, script, link",
      ),
    ).toBeNull();
    expect(
      container.querySelector("[src], [srcset], [href], [style]"),
    ).toBeNull();
    expect(container.innerHTML).not.toMatch(/url\s*\(/i);
    expect(iconStyles).not.toMatch(/url\s*\(|@import/i);
    expect(fetch).not.toHaveBeenCalled();
    expect(xhr).not.toHaveBeenCalled();
  });
});

describe("icon recommendation cards preserve engine data and actions", () => {
  it("keeps the label, suitability, costs, signed savings, and callbacks", () => {
    const onToggle = vi.fn();
    const onDetails = vi.fn();
    const item = {
      ...assessment.recommendations[1],
      standalone: assessment.scenario,
    };
    render(
      <RecommendationCard
        item={item}
        selected={false}
        onToggle={onToggle}
        onDetails={onDetails}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Air-source heat pump" }),
    ).toBeTruthy();
    expect(screen.getByText("Medium suitability")).toBeTruthy();
    expect(screen.getByText("£9,000–£15,000")).toBeTruthy();
    expect(screen.getByText(item.reason)).toBeTruthy();
    expect(screen.getByText("-2,720")).toBeTruthy();
    expect(screen.getByText("+9,600")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Add to plan" }));
    fireEvent.click(
      screen.getByRole("button", {
        name: "View details for Air-source heat pump",
      }),
    );
    expect(onToggle).toHaveBeenCalledOnce();
    expect(onDetails).toHaveBeenCalledOnce();
  });

  it("still blocks infeasible additions but allows removing an old selection", () => {
    const onToggle = vi.fn();
    const props = {
      item: { ...assessment.recommendations[0], feasible: false },
      onToggle,
      onDetails: vi.fn(),
    };
    const { rerender } = render(
      <RecommendationCard {...props} selected={false} />,
    );
    expect(screen.getByText("Not feasible")).toBeTruthy();
    const add = screen.getByRole("button", { name: "Add to plan" });
    expect(add).toHaveProperty("disabled", true);
    fireEvent.click(add);
    expect(onToggle).not.toHaveBeenCalled();
    rerender(<RecommendationCard {...props} selected />);
    const remove = screen.getByRole("button", { name: "Remove from plan" });
    expect(remove).toHaveProperty("disabled", false);
    fireEvent.click(remove);
    expect(onToggle).toHaveBeenCalledOnce();
  });

  it("does not replace unavailable standalone savings with zero", () => {
    render(
      <RecommendationCard
        item={{
          ...assessment.recommendations[0],
          standalone: {
            ...assessment.scenario,
            electricity_saving_kwh: null,
            gas_saving_kwh: null,
          },
        }}
        selected={false}
        onToggle={vi.fn()}
        onDetails={vi.fn()}
      />,
    );
    expect(screen.getAllByText("Unavailable")).toHaveLength(2);
  });
});
