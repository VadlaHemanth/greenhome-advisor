import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import App from "../App";
import { api } from "../api";
import * as catalogueApi from "../demoCatalogue";
import { assessment, catalogue, health, home } from "./fixtures";
import { catalogueFixture } from "./demoCatalogueFixtures";

beforeEach(() => {
  window.history.replaceState(null, "", "#examples");
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.spyOn(api, "workspace").mockResolvedValue(null);
  vi.spyOn(api, "homes").mockResolvedValue([home]);
  vi.spyOn(api, "catalogue").mockResolvedValue(catalogue);
  vi.spyOn(api, "health").mockResolvedValue(health);
  vi.spyOn(api, "assess").mockImplementation(async (input, selected) => ({
    ...assessment,
    home: input,
    selected_retrofits: selected || [],
  }));
  vi.spyOn(catalogueApi, "loadDemoCatalogue").mockResolvedValue(
    catalogueFixture(),
  );
});

it("opens a catalogue home with its exact facts as an unsaved temporary assessment", async () => {
  const create = vi.spyOn(api, "createWorkspace");
  render(<App />);
  await screen.findByRole("heading", { name: "Find a home to explore" });
  await screen.findByRole("heading", { name: "Fictional home 4" });
  fireEvent.click(
    screen.getByRole("button", { name: "Explore Fictional home 4" }),
  );
  await screen.findByRole("heading", { name: /A considered plan/ });
  const selector = screen.getByRole("combobox", { name: "Choose a home" });
  expect(selector).toHaveProperty("value", "CAT-004");
  expect(
    within(selector).getByRole("option", { name: /CAT-004/ }),
  ).toBeTruthy();
  expect(api.assess).toHaveBeenCalledWith(
    expect.objectContaining({ property_id: "CAT-004", floor_area_m2: 100 }),
    [],
    expect.any(AbortSignal),
  );
  expect(create).not.toHaveBeenCalled();
});

it("has a separate Examples link without replacing the saved Homes adviser view", async () => {
  render(<App />);
  await screen.findByRole("heading", { name: "Find a home to explore" });
  const nav = screen.getByRole("navigation", { name: "Main navigation" });
  expect(
    within(nav).getByRole("link", { name: "Examples" }).getAttribute("href"),
  ).toBe("#examples");
  expect(
    within(nav).getByRole("link", { name: "Homes" }).getAttribute("href"),
  ).toBe("#homes");
});

it("allows catalogue browsing even when the selected home assessment fails", async () => {
  vi.spyOn(api, "assess").mockRejectedValue(new Error("Assessment failed"));
  render(<App />);
  await screen.findByRole("heading", { name: "Fictional home 1" });
  expect(screen.queryByText("Assessment failed")).toBeNull();
});
