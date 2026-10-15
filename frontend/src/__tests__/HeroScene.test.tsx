import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HeroScene } from "../HeroScene";

describe("generated house artwork", () => {
  it("labels the image as a concept and loads only self-hosted responsive assets", () => {
    render(<HeroScene />);
    const image = screen.getByRole("img", {
      name: /AI-generated illustration/,
    });
    expect(image.getAttribute("src")).toBe("/assets/home-concept-chatgpt.webp");
    expect(image.getAttribute("srcset")).toContain(
      "/assets/home-concept-chatgpt-small.webp 640w",
    );
    expect(image.getAttribute("width")).toBe("1200");
    expect(image.getAttribute("height")).toBe("675");
    expect(image.getAttribute("loading")).toBe("eager");
    expect(image.getAttribute("fetchpriority")).toBe("high");
    expect(
      screen.getByText(/not the assessed property or evidence/),
    ).toBeTruthy();
  });

  it("preserves the layout and disclosure if the asset cannot load", () => {
    render(<HeroScene />);
    fireEvent.error(
      screen.getByRole("img", { name: /AI-generated illustration/ }),
    );
    expect(screen.getByText("House illustration unavailable")).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText(/AI-generated concept/)).toBeTruthy();
  });
});
